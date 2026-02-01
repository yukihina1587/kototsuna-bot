"""
Twitchプラットフォームアダプター

twitchioを使用してTwitchチャットに接続する。
"""

import asyncio
import aiohttp
import json
from typing import Optional, Callable, Any

from twitchio.ext import commands

from src.platforms.base import PlatformAdapter, PlatformType, SpecialEvent, EventType
from src.translator import translate_text
from src.logger import logger
from src.tts import get_tts_instance, is_japanese
from src.participant_tracker import get_tracker
from src.comment_data import create_twitch_comment, CommentData
from src.config import load_config


class EventSubHandler:
    """Twitch EventSub WebSocketハンドラー（フォロー検知用）"""

    EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"

    def __init__(self, token: str, client_id: str, channel_name: str, on_follow_callback: Callable[[str], None]):
        # oauth:プレフィックスを除去
        self.token = token[6:] if token.startswith("oauth:") else token
        self.client_id = client_id
        self.channel_name = channel_name.lower()
        self.on_follow = on_follow_callback
        self._running = False
        self._session_id: Optional[str] = None
        self._broadcaster_id: Optional[str] = None
        self._moderator_id: Optional[str] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """EventSub接続を開始"""
        if self._running:
            return

        self._running = True

        # ユーザーIDを取得
        try:
            self._broadcaster_id = await self._get_user_id(self.channel_name)
            if not self._broadcaster_id:
                logger.error(f"Failed to get broadcaster ID for {self.channel_name}")
                return

            # モデレーターID（BOTのID）を取得
            self._moderator_id = await self._get_token_user_id()
            if not self._moderator_id:
                logger.error("Failed to get moderator (bot) user ID")
                return

            logger.info(f"EventSub: broadcaster_id={self._broadcaster_id}, moderator_id={self._moderator_id}")
        except Exception as e:
            logger.error(f"EventSub setup failed: {e}", exc_info=True)
            return

        # WebSocket接続を開始
        self._task = asyncio.create_task(self._run_websocket())

    async def stop(self) -> None:
        """EventSub接続を停止"""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _get_user_id(self, login: str) -> Optional[str]:
        """ユーザー名からユーザーIDを取得"""
        url = f"https://api.twitch.tv/helix/users?login={login}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Client-Id": self.client_id,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            return data["data"][0]["id"]
        except Exception as e:
            logger.error(f"Failed to get user ID for {login}: {e}")
        return None

    async def _get_token_user_id(self) -> Optional[str]:
        """トークンの所有者のユーザーIDを取得"""
        url = "https://api.twitch.tv/helix/users"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Client-Id": self.client_id,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            return data["data"][0]["id"]
        except Exception as e:
            logger.error(f"Failed to get token user ID: {e}")
        return None

    async def _run_websocket(self) -> None:
        """WebSocket接続を維持"""
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self.EVENTSUB_URL) as ws:
                        self._ws = ws
                        logger.info("EventSub WebSocket connected")

                        async for msg in ws:
                            if not self._running:
                                break

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"EventSub WebSocket error: {ws.exception()}")
                                break
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.info("EventSub WebSocket closed")
                                break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"EventSub WebSocket error: {e}", exc_info=True)
                if self._running:
                    await asyncio.sleep(5)  # 再接続待機

    async def _handle_message(self, data: str) -> None:
        """WebSocketメッセージを処理"""
        try:
            message = json.loads(data)
            msg_type = message.get("metadata", {}).get("message_type")

            if msg_type == "session_welcome":
                self._session_id = message["payload"]["session"]["id"]
                logger.info(f"EventSub session established: {self._session_id}")
                # フォローイベントを購読
                await self._subscribe_to_follows()

            elif msg_type == "session_keepalive":
                pass  # キープアライブ

            elif msg_type == "notification":
                await self._handle_notification(message)

            elif msg_type == "session_reconnect":
                # 再接続が必要
                reconnect_url = message["payload"]["session"]["reconnect_url"]
                logger.info(f"EventSub reconnect requested: {reconnect_url}")

        except Exception as e:
            logger.error(f"Failed to handle EventSub message: {e}", exc_info=True)

    async def _subscribe_to_follows(self) -> None:
        """フォローイベントを購読"""
        url = "https://api.twitch.tv/helix/eventsub/subscriptions"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        }
        body = {
            "type": "channel.follow",
            "version": "2",
            "condition": {
                "broadcaster_user_id": self._broadcaster_id,
                "moderator_user_id": self._moderator_id,
            },
            "transport": {
                "method": "websocket",
                "session_id": self._session_id,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as resp:
                    if resp.status in (200, 202):
                        logger.info("EventSub: Subscribed to channel.follow")
                    else:
                        error = await resp.text()
                        logger.error(f"EventSub subscription failed: {resp.status} - {error}")
        except Exception as e:
            logger.error(f"Failed to subscribe to follows: {e}", exc_info=True)

    async def _handle_notification(self, message: dict) -> None:
        """通知イベントを処理"""
        subscription_type = message.get("payload", {}).get("subscription", {}).get("type")

        if subscription_type == "channel.follow":
            event = message["payload"]["event"]
            follower_name = event.get("user_name", "誰か")
            logger.info(f"New follower: {follower_name}")

            if self.on_follow:
                self.on_follow(follower_name)


class TwitchBot(commands.Bot):
    """Twitch IRC Bot（内部クラス）"""

    def __init__(
        self,
        token: str,
        channel: str,
        client_id: str,
        adapter: "TwitchAdapter",
    ):
        super().__init__(token=token, prefix='!', initial_channels=[channel])
        self.token = token
        self.channel_name = channel
        self.client_id = client_id
        self.adapter = adapter
        self._running_loop: Optional[asyncio.AbstractEventLoop] = None
        self._processed_message_ids: set[str] = set()
        self._max_processed_ids = 1000
        self._stopped = False
        self._eventsub_handler: Optional[EventSubHandler] = None

    async def event_ready(self) -> None:
        try:
            self._running_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._running_loop = None
        logger.info(f"Twitch Bot logged in as {self.nick}")

        # EventSub接続を開始（フォロー検知）
        if self.client_id:
            try:
                self._eventsub_handler = EventSubHandler(
                    token=self.token,
                    client_id=self.client_id,
                    channel_name=self.channel_name,
                    on_follow_callback=self._on_follow_event
                )
                await self._eventsub_handler.start()
                logger.info("EventSub handler started for follow detection")
            except Exception as e:
                logger.error(f"Failed to start EventSub handler: {e}", exc_info=True)
        else:
            logger.warning("client_id not provided, follow detection disabled")

        # アダプターに接続完了を通知
        self.adapter._on_connected()

    def _on_follow_event(self, follower_name: str) -> None:
        """フォローイベントのコールバック"""
        event = SpecialEvent(
            event_type=EventType.FOLLOW,
            message=f"{follower_name} さんがフォローしました",
            user_name=follower_name,
        )
        self.adapter._notify_event(event)

    async def event_message(self, message) -> None:
        if self._stopped:
            return

        if message.author is None:
            logger.debug("Skipped: message.author is None")
            return

        # メッセージIDによる重複チェック
        msg_id = message.tags.get('id') if message.tags else None
        if msg_id:
            if msg_id in self._processed_message_ids:
                logger.debug(f"Duplicate message skipped: {msg_id}")
                return
            self._processed_message_ids.add(msg_id)
            if len(self._processed_message_ids) > self._max_processed_ids:
                to_remove = list(self._processed_message_ids)[:self._max_processed_ids // 2]
                for old_id in to_remove:
                    self._processed_message_ids.discard(old_id)

        # BOTが送信した翻訳結果をスキップ
        if '\u200B' in message.content:
            logger.debug(f"Skipped (zero-width space): {message.author.name}")
            return

        is_bot_echo = message.echo and self.nick and message.author.name.lower() == self.nick.lower()
        if is_bot_echo:
            logger.debug(f"Skipped (bot echo): {message.author.name}")
            return

        # CommentDataを作成してアダプターに通知
        display_name = message.author.display_name if hasattr(message.author, 'display_name') else message.author.name
        comment = create_twitch_comment(
            username=message.author.name,
            message=message.content,
            tags=message.tags,
            display_name=display_name,
            translated=None
        )

        # アダプター経由でメッセージを処理
        await self.adapter._process_message(message, comment)

    async def event_usernotice(self, message) -> None:
        """サブスクやギフトなどのUSERNOTICEイベントを処理"""
        msg_id = message.tags.get("msg-id") if message.tags else None

        self_sub_types = {"sub", "resub", "primepaidupgrade"}
        gift_sub_types = {
            "subgift", "anonsubgift", "submysterygift",
            "anonsubmysterygift", "giftpaidupgrade",
            "rewardgift", "communitypayforward",
        }
        other_sub_types = {"bitsbadgetier"}

        all_sub_related = self_sub_types | gift_sub_types | other_sub_types
        if msg_id not in all_sub_related:
            return

        display_name = None
        if hasattr(message, "author") and message.author:
            display_name = getattr(message.author, "display_name", None) or getattr(message.author, "name", None)
        display_name = display_name or "匿名"

        system_msg = ""
        if message.tags and message.tags.get("system-msg"):
            system_msg = self._decode_irc_tag(message.tags.get("system-msg"))

        if msg_id in self_sub_types:
            event_type = EventType.SUBSCRIPTION
            fallback_msg = f"{display_name} がサブスク登録しました"
        elif msg_id in gift_sub_types:
            event_type = EventType.GIFT_SUB
            fallback_msg = f"{display_name} がギフトサブを贈りました"
        else:
            event_type = EventType.SUBSCRIPTION
            fallback_msg = f"{display_name} がサブスクしました"

        event = SpecialEvent(
            event_type=event_type,
            message=system_msg if system_msg else fallback_msg,
            user_name=display_name,
        )
        self.adapter._notify_event(event)

    @staticmethod
    def _decode_irc_tag(value: str) -> str:
        """Twitch IRCタグのエスケープを解除"""
        if not value:
            return ""
        replacements = {
            r"\s": " ",
            r"\:": ";",
            r"\\": "\\",
            r"\r": "\r",
            r"\n": "\n",
        }
        result = value
        for k, v in replacements.items():
            result = result.replace(k, v)
        return result

    def stop(self) -> None:
        """BOTを安全に停止"""
        logger.info("TwitchBot.stop() called")
        self._stopped = True
        loop = self._running_loop

        # EventSubハンドラーを停止
        if self._eventsub_handler and loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._eventsub_handler.stop(),
                    loop
                )
                logger.info("EventSub handler stop requested")
            except Exception as e:
                logger.warning(f"Exception stopping EventSub handler: {e}")
            self._eventsub_handler = None

        if loop is None:
            logger.info("No running loop, nothing to stop.")
            self._processed_message_ids.clear()
            return

        try:
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
                logger.info("Bot loop stop requested.")
        except Exception as e:
            logger.warning(f"Exception during loop stop: {e}")

        self._running_loop = None
        self._processed_message_ids.clear()
        logger.info("TwitchBot.stop() completed")


class TwitchAdapter(PlatformAdapter):
    """
    Twitchプラットフォームアダプター

    twitchioを使用してTwitchチャットに接続し、メッセージの受信・送信を行う。
    """

    def __init__(
        self,
        token: str,
        client_id: str,
        deepl_api_key: str,
        get_lang_mode: Callable[[], str],
        tts_enabled_getter: Callable[[], bool],
        tts_include_name_getter: Callable[[], bool],
        gui_ref: Any = None,
    ):
        super().__init__()
        self._token = token
        self._client_id = client_id
        self._deepl_api_key = deepl_api_key
        self._get_lang_mode = get_lang_mode
        self._tts_enabled_getter = tts_enabled_getter
        self._tts_include_name_getter = tts_include_name_getter
        self._gui = gui_ref
        self._bot: Optional[TwitchBot] = None
        self._tts = get_tts_instance()
        self._tracker = get_tracker()

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.TWITCH

    @property
    def bot(self) -> Optional[TwitchBot]:
        """内部のTwitchBotインスタンスを取得（後方互換性のため）"""
        return self._bot

    def _on_connected(self) -> None:
        """接続完了時の内部コールバック"""
        self._connected = True
        logger.info(f"TwitchAdapter connected to {self._channel}")

    async def connect(self, channel: str, **kwargs) -> bool:
        """Twitchチャンネルに接続"""
        if self._connected:
            logger.warning("Already connected")
            return False

        self._channel = channel
        self._bot = TwitchBot(
            token=self._token,
            channel=channel,
            client_id=self._client_id,
            adapter=self,
        )

        try:
            # BOTを起動（別スレッドで実行されることを想定）
            await self._bot.start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Twitch: {e}", exc_info=True)
            return False

    async def disconnect(self) -> None:
        """接続を切断"""
        if self._bot:
            self._bot.stop()
            self._bot = None
        self._connected = False
        self._channel = None
        logger.info("TwitchAdapter disconnected")

    async def send_message(self, message: str) -> bool:
        """チャットにメッセージを送信"""
        if not self._bot or not self._connected:
            logger.warning("Not connected, cannot send message")
            return False

        try:
            if self._bot._connection and self._bot._connection.connected_channels:
                channel = self._bot._connection.connected_channels[0]
                await channel.send(message)
                return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
        return False

    async def send_participant_list(self) -> bool:
        """参加者リストをチャットに送信"""
        participants = self._tracker.get_participant_names()

        if not participants:
            message = "【待機参加者リスト】参加者はいません"
        else:
            participant_str = "→".join(participants)
            message = f"【待機参加者リスト】{participant_str}"

        return await self.send_message(message)

    async def _process_message(self, raw_message, comment: CommentData) -> None:
        """メッセージを処理（翻訳・TTS・GUI通知）"""
        original_content = raw_message.content
        content = raw_message.content

        # エモート処理
        if raw_message.tags and raw_message.tags.get('emotes'):
            content = self._process_emotes(content, raw_message.tags['emotes'])

        # 参加者トラッキング
        participant_name = comment.display_name or comment.username
        added_by_keyword = self._tracker.check_message(participant_name, raw_message.content)

        if added_by_keyword:
            await self._handle_participant_join(raw_message, participant_name)
            return

        # 翻訳設定チェック
        config = load_config()
        if not config.get("chat_translation_enabled", False):
            # 翻訳なしでコメント表示
            self._notify_message(comment)
            self._speak_message(raw_message.content, comment)
            return

        # 翻訳実行
        lang_mode = self._get_lang_mode()
        translated = await translate_text(content, lang_mode, self._deepl_api_key)

        if translated == "":
            # フィルタでスキップ
            if self._gui:
                self._gui.log_message("🚫 翻訳フィルタによりスキップしました", log_type="system")
            self._notify_message(comment)
            return

        # <k>タグを除去
        if translated:
            translated = translated.replace("<k>", "").replace("</k>", "")

        # 翻訳結果をチャットに送信
        if translated and translated != raw_message.content:
            await self.send_message(f"[Chat] {translated}" + '\u200B')

        # コメントデータを更新
        comment.translated = translated if translated and translated != raw_message.content else None
        self._notify_message(comment)

        # TTS
        self._speak_message(raw_message.content, comment, translated)

        # ビッツイベント検知
        self._check_bits_event(raw_message, original_content)

    def _process_emotes(self, content: str, emote_str: str) -> str:
        """エモートを<k>タグでラップ"""
        replacements = []
        for emote_group in emote_str.split('/'):
            if ':' in emote_group:
                _, positions = emote_group.split(':')
                for pos in positions.split(','):
                    start, end = map(int, pos.split('-'))
                    replacements.append((start, end + 1))

        replacements.sort(key=lambda x: x[0], reverse=True)
        temp_content = list(content)
        for start, end in replacements:
            original = "".join(temp_content[start:end])
            temp_content[start:end] = list(f"<k>{original}</k>")

        return "".join(temp_content)

    async def _handle_participant_join(self, raw_message, participant_name: str) -> None:
        """参加者登録の処理"""
        join_msg = f"{participant_name}さんが参加希望登録しました。"
        join_comment = create_twitch_comment(
            username=raw_message.author.name,
            message=join_msg,
            tags=raw_message.tags,
            display_name=participant_name,
            translated=None
        )
        self._notify_message(join_comment)

        if self._gui:
            self._gui.log_message(join_msg, log_type="system")
            try:
                self._gui.send_participant_list_to_chat()
            except Exception as e:
                logger.error(f"Failed to auto-send participant list: {e}", exc_info=True)

        if self._tts_enabled_getter():
            try:
                self._tts.speak(join_msg)
            except Exception as e:
                logger.error(f"TTS speak error: {e}", exc_info=True)

    def _speak_message(self, original: str, comment: CommentData, translated: Optional[str] = None) -> None:
        """TTSでメッセージを読み上げ"""
        if not self._tts_enabled_getter():
            return

        speak_text = original

        if translated and translated != original:
            if is_japanese(translated):
                speak_text = translated

        if self._tts_include_name_getter():
            display_name = comment.display_name or comment.username
            speak_text = f"{display_name}さん、{speak_text}"

        if speak_text and speak_text.strip():
            try:
                self._tts.speak(speak_text)
                logger.debug(f"TTS speak: {speak_text[:30]}...")
            except Exception as e:
                logger.error(f"TTS speak error: {e}", exc_info=True)

    def _check_bits_event(self, raw_message, original_content: str) -> None:
        """ビッツイベントをチェック"""
        bits = 0
        if raw_message.tags and raw_message.tags.get("bits"):
            try:
                bits = int(raw_message.tags.get("bits", "0"))
            except ValueError:
                bits = 0

        if bits > 0:
            display_name = None
            if hasattr(raw_message, "author") and raw_message.author:
                display_name = getattr(raw_message.author, "display_name", None) or getattr(raw_message.author, "name", None)
            display_name = display_name or "匿名"

            bits_msg = f"{display_name} が {bits} ビッツを投げました"
            if original_content:
                bits_msg += f"「{original_content}」"

            event = SpecialEvent(
                event_type=EventType.BITS,
                message=bits_msg,
                user_name=display_name,
                amount=bits,
            )
            self._notify_event(event)


# 後方互換性のためのエイリアス
TranslateBot = TwitchBot
