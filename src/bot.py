import asyncio
import aiohttp
import json
import threading
import time
from twitchio.ext import commands
from types import SimpleNamespace
from src.translator import translate_text, translate_text_batched, should_filter, apply_translation_dictionary, get_stats
from src.logger import logger
from src.tts import get_tts_instance, is_japanese
from src.participant_tracker import get_tracker
from src.comment_data import create_twitch_comment
from src.config import load_config, save_config, VALID_TRANSLATE_MODES
from src.commands import PermissionLevel, CooldownManager, check_permission, substitute_variables
from src.commands_store import CommandStore
from src.emote_provider import EmoteProvider
from src.tts_dictionary import get_dictionary
from src.viewer_store import get_viewer_store
from src.channel_manager import search_game, update_channel_info
from src.plugin_manager import get_plugin_manager
from src.session_archive import get_session_archive
from src.bot_filter import BotFilter
from src.games import (
    fortune, roll_dice, coin_toss, spin_slot, spin_roulette,
    play_janken, get_number_guess_game, get_giveaway_manager,
)


class EventSubHandler:
    """Twitch EventSub WebSocketハンドラー（フォロー検知用）"""

    EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"

    def __init__(self, token: str, client_id: str, channel_name: str, on_follow_callback):
        # oauth:プレフィックスを除去
        self.token = token[6:] if token.startswith("oauth:") else token
        self.client_id = client_id
        self.channel_name = channel_name.lower()
        self.on_follow = on_follow_callback
        self._running = False
        self._session_id = None
        self._broadcaster_id = None
        self._moderator_id = None
        self._ws = None
        self._task = None

    async def start(self):
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

    async def stop(self):
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

    async def _get_user_id(self, login: str) -> str | None:
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

    async def _get_token_user_id(self) -> str | None:
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

    async def _run_websocket(self):
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

    async def _handle_message(self, data: str):
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

    async def _subscribe_to_follows(self):
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

    async def _handle_notification(self, message: dict):
        """通知イベントを処理"""
        subscription_type = message.get("payload", {}).get("subscription", {}).get("type")

        if subscription_type == "channel.follow":
            event = message["payload"]["event"]
            follower_name = event.get("user_name", "誰か")
            logger.info(f"New follower: {follower_name}")

            if self.on_follow:
                self.on_follow(follower_name)

class TranslateBot(commands.Bot):
    def __init__(self, token, channel, get_lang_mode, gui_ref,
                 tts_enabled_getter=None, tts_include_name_getter=None, client_id=None):
        super().__init__(token=token, prefix='!', initial_channels=[channel])
        self._initialize_state(
            token=token,
            channel=channel,
            get_lang_mode=get_lang_mode,
            gui_ref=gui_ref,
            tts_enabled_getter=tts_enabled_getter,
            tts_include_name_getter=tts_include_name_getter,
            client_id=client_id,
        )

    def _initialize_state(
        self,
        *,
        token,
        channel,
        get_lang_mode,
        gui_ref,
        tts_enabled_getter=None,
        tts_include_name_getter=None,
        client_id=None,
    ):
        self.token = token
        self.channel_name = channel

        self.client_id = client_id
        self.get_lang_mode = get_lang_mode
        self.gui = gui_ref
        self.tts_enabled_getter = tts_enabled_getter or (lambda: False)
        self.tts_include_name_getter = tts_include_name_getter or (lambda: False)
        self.tts = get_tts_instance()
        self.tracker = get_tracker()
        # 実行中のイベントループは event_ready でセットする
        self._running_loop = None
        # 処理済みメッセージIDを記録（重複防止）
        self._processed_message_ids = set()
        self._max_processed_ids = 1000  # メモリ制限
        # 停止フラグ
        self._stopped = False
        # コマンド機能
        self._command_store = CommandStore()
        self._cooldown_manager = CooldownManager()
        config = load_config()
        self._commands_enabled = config.get("commands_enabled", True)
        # EventSub handler（フォロー検知用）
        self._eventsub_handler = None
        # Third-party emote provider (BTTV/FFZ/7TV)
        self._emote_provider = EmoteProvider()
        # Viewer store（視聴回数・ボイス割り当て）
        self._viewer_store = get_viewer_store()
        # Plugin manager（わんコメ互換 plugin.js ホスト）
        self._plugin_manager = get_plugin_manager()
        # BOT フィルタリング
        self._bot_filter = BotFilter(
            enabled=config.get("bot_filter_enabled", True),
            custom_bots=config.get("bot_filter_custom", []),
        )
        # セッションアーカイブ
        self._archive_enabled = config.get("archive_enabled", True)
        self._archive = get_session_archive() if self._archive_enabled else None

    @classmethod
    def create_test_dispatcher(
        cls,
        *,
        token,
        channel,
        get_lang_mode,
        gui_ref,
        tts_enabled_getter=None,
        tts_include_name_getter=None,
        client_id=None,
    ):
        """コメントテスター専用の軽量インスタンスを作成する。"""
        bot = cls.__new__(cls)
        bot._initialize_state(
            token=token,
            channel=channel,
            get_lang_mode=get_lang_mode,
            gui_ref=gui_ref,
            tts_enabled_getter=tts_enabled_getter,
            tts_include_name_getter=tts_include_name_getter,
            client_id=client_id,
        )
        return bot

    async def event_ready(self):
        # GUI側から run_coroutine_threadsafe で送信できるよう、実際に動いているループを保持
        try:
            self._running_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._running_loop = None
        logger.info(f"Bot logged in as {self.nick}")

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

        # Load third-party emotes (BTTV/FFZ/7TV)
        broadcaster_id = None
        if self._eventsub_handler:
            broadcaster_id = getattr(self._eventsub_handler, '_broadcaster_id', None)
        if broadcaster_id:
            self._emote_provider.set_channel_id(broadcaster_id)
        await asyncio.to_thread(self._emote_provider.load_emotes)
        logger.info(f"Third-party emotes loaded: {self._emote_provider.emote_count}")

        # 接続成功: GUI に通知してチャンネル履歴を更新
        if self.gui and hasattr(self.gui, 'on_channel_connected'):
            try:
                display_name = self.nick or self.channel_name
                user_id = str(broadcaster_id) if broadcaster_id else ""
                self.gui.master.after(0, lambda: self.gui.on_channel_connected(
                    self.channel_name, display_name, user_id
                ))
            except Exception as e:
                logger.debug(f"on_channel_connected callback failed: {e}")

        # Kototsuna プラグインを読み込む（わんコメ互換 plugin.js）
        self._plugin_manager = get_plugin_manager()
        await asyncio.to_thread(self._plugin_manager.load_plugins)
        if self._plugin_manager.count > 0:
            logger.info(f"Kototsuna plugins loaded: {self._plugin_manager.count}")

        # セッションアーカイブを開始
        if self._archive:
            try:
                self._archive.open()
                self._archive.start_session(self.channel_name)
                # 起動時に保持期間超過データをクリーンアップ
                config = load_config()
                retention = config.get("archive_retention_days", 90)
                if retention > 0:
                    removed = self._archive.cleanup(retention)
                    if removed > 0:
                        logger.info(f"Archive cleanup removed {removed} old sessions")
            except Exception as e:
                logger.error(f"Failed to start session archive: {e}", exc_info=True)

    def _call_gui(self, callback_name: str, *args, **kwargs) -> None:
        """GUI更新をメインスレッドへ橋渡しする。"""
        if not self.gui:
            return
        callback = getattr(self.gui, callback_name, None)
        if not callable(callback):
            return
        trace_id = None
        if args:
            raw_data = getattr(args[0], "raw_data", None) or {}
            trace_id = raw_data.get("id")
        if threading.current_thread() is threading.main_thread():
            if trace_id:
                logger.info(f"[tester:{trace_id}] bot._call_gui immediate callback={callback_name}")
            callback(*args, **kwargs)
            return
        if hasattr(self.gui, "master"):
            if trace_id:
                logger.info(f"[tester:{trace_id}] bot._call_gui scheduled callback={callback_name}")
            self.gui.master.after(0, lambda: callback(*args, **kwargs))
            return
        if trace_id:
            logger.info(f"[tester:{trace_id}] bot._call_gui fallback callback={callback_name}")
        callback(*args, **kwargs)

    def _on_follow_event(self, follower_name: str):
        """フォローイベントのコールバック"""
        follow_msg = f"{follower_name} さんがフォローしました"
        self._notify_special_event(follow_msg, event_type="follow")

    async def event_message(self, message):
        # 停止済みの場合は処理しない
        if self._stopped:
            return

        # message.authorがNoneの場合は処理しない（BOTのエコーメッセージなど）
        if message.author is None:
            logger.debug("Skipped: message.author is None")
            return

        # メッセージIDによる重複チェック（BOT再起動時の二重処理防止）
        msg_id = message.tags.get('id') if message.tags else None
        if msg_id:
            if msg_id in self._processed_message_ids:
                logger.debug(f"Duplicate message skipped: {msg_id}")
                return
            self._processed_message_ids.add(msg_id)
            # メモリ制限: 古いIDを削除
            if len(self._processed_message_ids) > self._max_processed_ids:
                # セットの最初の半分を削除
                to_remove = list(self._processed_message_ids)[:self._max_processed_ids // 2]
                for old_id in to_remove:
                    self._processed_message_ids.discard(old_id)

        # BOTが送信した翻訳結果をスキップ（ゼロ幅スペースで判定）
        if '\u200B' in message.content:
            logger.debug(f"Skipped (zero-width space): {message.author.name}")
            return

        # BOTが送信したエコーメッセージのみスキップ
        # ※配信者アカウント＝BOTアカウントの場合、配信者の手入力は翻訳対象
        # echoフラグ: BOTが送信→Twitchからエコーバック→True
        # 配信者の手入力: echo=False（通常メッセージとして扱われる）
        is_bot_echo = message.echo and self.nick and message.author.name.lower() == self.nick.lower()
        if is_bot_echo:
            logger.debug(f"Skipped (bot echo): {message.author.name}")
            return

        # 配信者の手入力（echo=False, 名前一致）は翻訳対象として処理を継続
        if self.nick and message.author.name.lower() == self.nick.lower():
            logger.debug(f"Processing broadcaster's own message: {message.author.name}")

        # === BOT フィルタリング ===
        # 誤 BAN 対策: チャンネルオーナーと認証ユーザー（配信者 BOT 兼用時）は絶対に除外しない
        author_name = getattr(message.author, "name", "") or ""
        protected = {self.channel_name, self.nick or ""}
        if self._bot_filter.is_bot(author_name, protected_names=protected):
            logger.debug(f"BOT フィルター: {author_name} をスキップ")
            return

        # === 視聴回数の記録 ===
        visit_display_name = (
            getattr(message.author, "display_name", None) or message.author.name
        )
        self._viewer_store.record_visit(message.author.name, visit_display_name)

        # === コマンド処理（翻訳より先に実行）===
        if self._commands_enabled and message.content.startswith('!'):
            cmd_handled = await self._handle_command(message)
            if cmd_handled:
                return

        original_content = message.content

        # ビッツ（チア）イベント検知と通知（早期returnの前に実行）
        bits = 0
        if message.tags and message.tags.get("bits"):
            try:
                bits = int(message.tags.get("bits", "0"))
            except ValueError:
                bits = 0

        if bits > 0:
            bits_display_name = None
            if hasattr(message, "author") and message.author:
                bits_display_name = getattr(message.author, "display_name", None) or getattr(message.author, "name", None)
            bits_display_name = bits_display_name or "匿名"

            bits_msg = f"{bits_display_name} が {bits} ビッツを投げました"
            if original_content:
                bits_msg += f"「{original_content}」"

            self._notify_special_event(bits_msg, event_type="bits")

        content = message.content
        replacements = []

        # Standard Twitch emotes (from IRC tags)
        if message.tags and message.tags.get('emotes'):
            emote_str = message.tags['emotes']
            for emote_group in emote_str.split('/'):
                if ':' in emote_group:
                    _, positions = emote_group.split(':')
                    for pos in positions.split(','):
                        start, end = map(int, pos.split('-'))
                        replacements.append((start, end + 1, 'emote'))

        # Third-party emotes (BTTV/FFZ/7TV) - text-based detection
        twitch_positions = [(s, e) for s, e, _ in replacements]
        tp_emotes = self._emote_provider.detect_emotes(
            message.content, twitch_positions
        )
        for emote in tp_emotes:
            replacements.append((emote['start'], emote['end'] + 1, 'emote'))

        # Refresh emote cache in background if stale
        self._emote_provider.refresh_if_stale()

        # 翻訳前後でエモート位置が崩れないよう、一時的に <k> タグで保護する
        if replacements:
            replacements.sort(key=lambda x: x[0], reverse=True)
            temp_content = list(content)
            for start, end, _ in replacements:
                original = "".join(temp_content[start:end])
                temp_content[start:end] = list(f"<k>{original}</k>")
            content = "".join(temp_content)

        # チャット発言者を参加者として記録（キーワード検知のみ）
        participant_name = getattr(message.author, "display_name", None) or message.author.name
        added_by_keyword = self.tracker.check_message(participant_name, message.content)

        # 参加キーワードを検知した場合は専用メッセージを表示・読み上げ
        if added_by_keyword:
            join_msg = f"{participant_name}さんが参加希望登録しました。"
            # コメントログに追加するため、専用CommentDataを生成
            join_comment = create_twitch_comment(
                username=message.author.name,
                message=join_msg,
                tags=message.tags,
                display_name=participant_name,
                translated=None
            )
            self._call_gui("on_comment_received", join_comment)
            self._call_gui("log_message", join_msg, log_type="system")

            # 参加者リストを即時送信
            try:
                self.gui.send_participant_list_to_chat()
            except Exception as e:
                logger.error(f"Failed to auto-send participant list: {e}", exc_info=True)

            # TTSで読み上げ（設定ONの場合）
            if self.tts_enabled_getter():
                speak_text = join_msg
                try:
                    self.tts.speak(speak_text)
                    logger.debug(f"TTS speak (join): {speak_text[:30]}...")
                except Exception as e:
                    logger.error(f"TTS speak error: {e}", exc_info=True)
            return

        # ここから通常の翻訳処理
        # プラグインの filterComment を通す
        if self._plugin_manager.count > 0:
            plugin_comment = create_twitch_comment(
                username=message.author.name,
                message=message.content,
                tags=message.tags,
                display_name=message.author.display_name if hasattr(message.author, 'display_name') else message.author.name,
            )
            filtered = await asyncio.to_thread(
                self._plugin_manager.filter_comment,
                plugin_comment.to_onecomme_dict(),
                "twitch",
            )
            if filtered is None:
                logger.debug(f"Comment blocked by plugin: {message.author.name}")
                return
            # プラグインがコメント本文を書き換えた場合は content を更新
            new_text = filtered.get("data", {}).get("comment")
            if new_text and new_text != message.content:
                content = new_text

        # チャット翻訳が無効の場合は翻訳をスキップ
        config = load_config()
        if not config.get("chat_translation_enabled", False):
            # 翻訳せずに原文のみ表示
            comment = create_twitch_comment(
                username=message.author.name,
                message=message.content,
                tags=message.tags,
                display_name=message.author.display_name if hasattr(message.author, 'display_name') else message.author.name,
                translated=None,
                extra_emotes=tp_emotes,
            )
            self._call_gui("on_comment_received", comment)
            self._archive_comment(comment, bits)

            # TTS: チャット読み上げ（翻訳無効時も原文を読み上げる）
            if self.tts_enabled_getter():
                speak_text = message.content
                if self.tts_include_name_getter():
                    display_name = message.author.display_name if hasattr(message.author, 'display_name') else message.author.name
                    speak_text = f"{display_name}さん、{speak_text}"
                if speak_text and speak_text.strip():
                    try:
                        voice_override = self._viewer_store.get_assigned_voice(
                            message.author.name
                        )
                        self.tts.speak(speak_text, speaker_id=voice_override)
                        logger.debug(f"TTS speak called (no translation): {speak_text[:30]}...")
                    except Exception as e:
                        logger.error(f"TTS speak error: {e}", exc_info=True)
            return

        lang_mode = self.get_lang_mode()
        translated = await translate_text_batched(content, lang_mode)

        # フィルタでスキップされた場合
        if translated == "":
            self._call_gui("log_message", "🚫 翻訳フィルタによりスキップしました", log_type="system")
            # コメントは表示する
            comment = create_twitch_comment(
                username=message.author.name,
                message=message.content,
                tags=message.tags,
                display_name=message.author.display_name if hasattr(message.author, 'display_name') else message.author.name,
                translated=None,
                extra_emotes=tp_emotes,
            )
            self._call_gui("on_comment_received", comment)
            return

        # Remove <k> tags from translated text for display
        if translated:
            translated = translated.replace("<k>", "").replace("</k>", "")

        # チャットに翻訳結果を送信（翻訳がある場合のみ）
        if translated and translated != message.content:
            await message.channel.send(f"[Chat] {translated}" + '\u200B')

        # 2言語目チャット翻訳（設定されている場合）
        lang_mode_2 = config.get("translate_mode_2", "")
        if lang_mode_2 and lang_mode_2 != lang_mode:
            translated_2 = await translate_text_batched(content, lang_mode_2)
            if translated_2:
                translated_2 = translated_2.replace("<k>", "").replace("</k>", "")
            if translated_2 and translated_2 != message.content and translated_2 != translated:
                await message.channel.send(f"[Chat2] {translated_2}" + '\u200B')

        # CommentDataオブジェクトを作成（全てのコメントを表示）
        comment = create_twitch_comment(
            username=message.author.name,
            message=message.content,
            tags=message.tags,
            display_name=message.author.display_name if hasattr(message.author, 'display_name') else message.author.name,
            translated=translated if translated and translated != message.content else None,
            extra_emotes=tp_emotes,
        )

        # GUIにコメントデータを渡す（全てのコメントをタイル表示）
        self._call_gui("on_comment_received", comment)

        # セッションアーカイブに記録
        self._archive_comment(comment, bits)

        # TTS: チャット読み上げ
        if self.tts_enabled_getter():
            # デフォルトは原文
            speak_text = message.content

            # 翻訳があり、かつ翻訳結果が日本語を含むなら、翻訳結果を読み上げる
            # (英語コメント -> 日本語翻訳 のケース)
            if translated and translated != message.content:
                if is_japanese(translated):
                    speak_text = translated

            # 名前を読み上げる設定があれば、名前も追加
            if self.tts_include_name_getter():
                display_name = message.author.display_name if hasattr(message.author, 'display_name') else message.author.name
                speak_text = f"{display_name}さん、{speak_text}"

            # TTSに渡す（空でないことを確認）
            if speak_text and speak_text.strip():
                try:
                    voice_override = self._viewer_store.get_assigned_voice(
                        message.author.name
                    )
                    self.tts.speak(speak_text, speaker_id=voice_override)
                    logger.debug(f"TTS speak called: {speak_text[:30]}...")
                except Exception as e:
                    logger.error(f"TTS speak error: {e}", exc_info=True)

    async def process_test_message(
        self,
        *,
        username: str,
        content: str,
        tags: dict | None = None,
        display_name: str | None = None,
    ) -> None:
        """コメントテスター用に、実チャット相当の経路でメッセージを処理する。"""
        safe_tags = dict(tags or {})
        safe_tags.setdefault("id", f"test-{time.monotonic_ns()}")
        safe_tags.setdefault("color", "#FF6B6B")
        safe_tags.setdefault("user-id", "test-000")
        badges = safe_tags.get("badges", {}) or {}
        trace_id = safe_tags["id"]
        logger.info(
            f"[tester:{trace_id}] process_test_message start "
            f"user={username} display={display_name or username} content={content[:80]!r}"
        )

        author = SimpleNamespace(
            name=username,
            display_name=display_name or username,
            is_mod="moderator" in badges,
            is_subscriber="subscriber" in badges,
            badges=badges,
        )

        async def _send_local(text: str) -> None:
            clean_text = (text or "").replace('\u200B', '').strip()
            if not clean_text or not self.gui:
                logger.info(f"[tester:{trace_id}] process_test_message local response skipped")
                return

            bot_name = (self.nick or "ことつなBOT").strip() or "ことつなBOT"
            bot_username = bot_name.lower().replace(" ", "_")
            response_tags = {
                "id": f"test-bot-{time.monotonic_ns()}",
                "color": "#60A5FA",
                "user-id": "test-bot",
                "badges": {},
                "tester_generated": True,
                "suppress_subtitle": True,
            }
            comment = create_twitch_comment(
                username=bot_username,
                message=clean_text,
                tags=response_tags,
                display_name=bot_name,
                translated=None,
            )
            logger.info(
                f"[tester:{trace_id}] process_test_message local response "
                f"bot_message={clean_text[:80]!r}"
            )
            self._call_gui("on_comment_received", comment)

        message = SimpleNamespace(
            content=content,
            author=author,
            channel=SimpleNamespace(send=_send_local),
            tags=safe_tags,
            echo=False,
        )
        logger.info(f"[tester:{trace_id}] process_test_message before event_message")
        await self.event_message(message)
        logger.info(f"[tester:{trace_id}] process_test_message done")


    def _archive_comment(self, comment, bits: int = 0) -> None:
        """コメントをセッションアーカイブに記録する。"""
        if not self._archive or not self._archive._current_session_id:
            return
        if getattr(comment, "raw_data", {}).get("tester_generated"):
            return
        try:
            self._archive.add_comment(
                username=comment.username,
                display_name=comment.display_name,
                original_text=comment.message,
                translated_text=comment.translated,
                source_lang=getattr(comment, "original_language", None),
                bits=bits,
                is_sub=comment.is_subscriber,
            )
        except Exception as e:
            logger.debug(f"Archive add_comment error: {e}")

    async def _handle_command(self, message) -> bool:
        """コマンドメッセージを処理する。

        カスタムコマンド → ビルトインコマンドの順で照合する。
        一致しない場合は False を返し、通常の翻訳フローに戻す。
        """
        content = message.content.strip()
        parts = content.split(maxsplit=1)
        cmd_name = parts[0][1:].lower()  # "!" を除去
        args = parts[1] if len(parts) > 1 else ""

        if not cmd_name:
            return False

        # --- カスタムコマンド ---
        custom = self._command_store.get(cmd_name)
        if custom and custom.enabled:
            # 権限チェック
            required = PermissionLevel(custom.permission)
            if not check_permission(message.author, required, self.channel_name):
                return True  # 権限不足でも消費（翻訳しない）

            # クールダウンチェック
            user_name = message.author.name.lower()
            allowed, remaining = self._cooldown_manager.check(
                cmd_name, user_name, custom.cooldown_global, custom.cooldown_user
            )
            if not allowed:
                return True  # クールダウン中でも消費

            self._cooldown_manager.record(cmd_name, user_name)
            response = substitute_variables(custom.response, message.author, self.channel_name)
            await message.channel.send(response + '\u200B')
            logger.info("カスタムコマンド実行: !%s by %s", cmd_name, user_name)
            return True

        # --- ビルトインコマンド ---
        builtin_handlers = {
            "help": self._cmd_help,
            "translate": self._cmd_translate,
            "lang": self._cmd_lang,
            "tts": self._cmd_tts,
            "translation": self._cmd_translation,
            "voicechat": self._cmd_voicechat,
            "lang2": self._cmd_lang2,
            "voicelang": self._cmd_voicelang,
            "voicelang2": self._cmd_voicelang2,
            "dict": self._cmd_dict,
            "voice": self._cmd_voice,
            "myvoice": self._cmd_myvoice,
            "visits": self._cmd_visits,
            "queue": self._cmd_queue,
            "leave": self._cmd_leave,
            "stream": self._cmd_stream,
            # ゲームコマンド
            "fortune": self._cmd_fortune,
            "dice": self._cmd_dice,
            "coin": self._cmd_coin,
            "slot": self._cmd_slot,
            "roulette": self._cmd_roulette,
            "janken": self._cmd_janken,
            "startguess": self._cmd_startguess,
            "guess": self._cmd_guess,
            "endguess": self._cmd_endguess,
            "giveaway": self._cmd_giveaway,
            "enter": self._cmd_enter,
            # 後方互換エイリアス
            "remove": self._cmd_remove,
            "clearall": self._cmd_clearall,
            "nextround": self._cmd_nextround,
            "roundreset": self._cmd_roundreset,
            "played": self._cmd_played,
        }

        handler = builtin_handlers.get(cmd_name)
        if handler:
            try:
                await handler(message, args)
            except Exception as e:
                logger.error("ビルトインコマンドエラー: !%s - %s", cmd_name, e, exc_info=True)
            return True

        # コマンド不一致 → 通常フローへ
        return False

    async def _cmd_help(self, message, args: str) -> None:
        """!help — 使用可能なコマンド一覧を表示"""
        builtin_cmds = [
            "!help", "!translate", "!lang", "!lang2",
            "!tts", "!translation", "!voicechat", "!voicelang", "!voicelang2",
            "!dict", "!voice", "!myvoice", "!visits",
            "!queue", "!leave", "!nextround", "!roundreset", "!played", "!stream",
            "!fortune", "!dice", "!coin", "!slot", "!roulette", "!janken",
            "!startguess", "!guess", "!endguess", "!giveaway", "!enter",
        ]
        custom_cmds = [
            f"!{c.name}" for c in self._command_store.list_all() if c.enabled
        ]
        all_cmds = builtin_cmds + custom_cmds
        response = f"コマンド一覧: {', '.join(all_cmds)}"
        await message.channel.send(response + '\u200B')

    async def _cmd_translate(self, message, args: str) -> None:
        """!translate <text> — テキストを翻訳"""
        if not args:
            await message.channel.send("使い方: !translate <テキスト>" + '\u200B')
            return
        lang_mode = self.get_lang_mode()
        translated = await translate_text_batched(args, lang_mode)
        if translated and translated != args:
            await message.channel.send(f"[翻訳] {translated}" + '\u200B')
            if self.tts_enabled_getter():
                self.tts.speak(translated)
        else:
            await message.channel.send("翻訳結果が同じか、翻訳できませんでした" + '\u200B')

    async def _cmd_lang(self, message, args: str) -> None:
        """!lang — 現在の翻訳モードを表示"""
        config = load_config()
        lang_mode = self.get_lang_mode()
        lang_mode_2 = config.get("translate_mode_2", "") or "off"
        voice_lang = config.get("voice_chat_lang", "日→英")
        voice_lang_2 = config.get("voice_chat_lang_2", "") or "off"
        await message.channel.send(
            f"翻訳モード: {lang_mode} / 言語2: {lang_mode_2} / 音声言語1: {voice_lang} / 音声言語2: {voice_lang_2}" + '\u200B'
        )

    async def _cmd_tts(self, message, args: str) -> None:
        """!tts on/off — TTS有効/無効切替（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        arg = args.strip().lower()
        if arg == "on":
            if hasattr(self.gui, 'tts_enabled') and hasattr(self.gui.tts_enabled, 'set'):
                self.gui.tts_enabled.set(True)
            await message.channel.send("TTS を有効にしました" + '\u200B')
        elif arg == "off":
            if hasattr(self.gui, 'tts_enabled') and hasattr(self.gui.tts_enabled, 'set'):
                self.gui.tts_enabled.set(False)
            await message.channel.send("TTS を無効にしました" + '\u200B')
        else:
            status = "ON" if self.tts_enabled_getter() else "OFF"
            await message.channel.send(f"TTS: {status} (使い方: !tts on/off)" + '\u200B')

    async def _cmd_translation(self, message, args: str) -> None:
        """!translation on/off — チャット翻訳の有効/無効切替（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        arg = args.strip().lower()
        if arg == "on":
            if hasattr(self.gui, 'chat_translation_enabled') and hasattr(self.gui.chat_translation_enabled, 'set'):
                self.gui.chat_translation_enabled.set(True)
                if hasattr(self.gui, '_on_translation_toggle_changed'):
                    self.gui._on_translation_toggle_changed()
            await message.channel.send("チャット翻訳を有効にしました" + '\u200B')
        elif arg == "off":
            if hasattr(self.gui, 'chat_translation_enabled') and hasattr(self.gui.chat_translation_enabled, 'set'):
                self.gui.chat_translation_enabled.set(False)
                if hasattr(self.gui, '_on_translation_toggle_changed'):
                    self.gui._on_translation_toggle_changed()
            await message.channel.send("チャット翻訳を無効にしました" + '\u200B')
        else:
            enabled = False
            if hasattr(self.gui, 'chat_translation_enabled') and hasattr(self.gui.chat_translation_enabled, 'get'):
                enabled = self.gui.chat_translation_enabled.get()
            status = "ON" if enabled else "OFF"
            await message.channel.send(f"チャット翻訳: {status} (使い方: !translation on/off)" + '\u200B')

    async def _cmd_voicechat(self, message, args: str) -> None:
        """!voicechat on/off — 声→翻訳チャットの有効/無効切替（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        arg = args.strip().lower()
        if arg in ("on", "off"):
            target = arg == "on"
            if hasattr(self.gui, 'voice_var') and hasattr(self.gui.voice_var, 'get'):
                current = self.gui.voice_var.get()
                if current == target:
                    status = "ON" if target else "OFF"
                    await message.channel.send(f"声→翻訳チャットは既に {status} です" + '\u200B')
                    return
                self.gui.voice_var.set(target)
                if hasattr(self.gui, 'toggle_voice'):
                    self.gui.toggle_voice()
            status = "有効" if target else "無効"
            await message.channel.send(f"声→翻訳チャットを{status}にしました" + '\u200B')
        else:
            enabled = False
            if hasattr(self.gui, 'voice_var') and hasattr(self.gui.voice_var, 'get'):
                enabled = self.gui.voice_var.get()
            status = "ON" if enabled else "OFF"
            await message.channel.send(f"声→翻訳チャット: {status} (使い方: !voicechat on/off)" + '\u200B')

    async def _cmd_lang2(self, message, args: str) -> None:
        """!lang2 [自動|英→日|日→英|off] — チャット翻訳2言語目を設定（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        arg = args.strip()
        config = load_config()
        if not arg:
            current = config.get("translate_mode_2", "") or "off"
            await message.channel.send(f"翻訳言語2: {current} (使い方: !lang2 自動/英→日/日→英/off)" + '\u200B')
            return
        if arg == "off":
            config["translate_mode_2"] = ""
            save_config(config)
            await message.channel.send("翻訳言語2を無効にしました" + '\u200B')
        elif arg in VALID_TRANSLATE_MODES:
            config["translate_mode_2"] = arg
            save_config(config)
            await message.channel.send(f"翻訳言語2を {arg} に設定しました" + '\u200B')
        else:
            await message.channel.send("使い方: !lang2 自動/英→日/日→英/off" + '\u200B')

    async def _cmd_voicelang(self, message, args: str) -> None:
        """!voicelang [自動|英→日|日→英] — 音声チャット翻訳言語1を設定（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        arg = args.strip()
        config = load_config()
        if not arg:
            current = config.get("voice_chat_lang", "日→英")
            await message.channel.send(f"音声チャット言語1: {current} (使い方: !voicelang 自動/英→日/日→英)" + '\u200B')
            return
        if arg in VALID_TRANSLATE_MODES:
            config["voice_chat_lang"] = arg
            save_config(config)
            await message.channel.send(f"音声チャット言語1を {arg} に設定しました" + '\u200B')
        else:
            await message.channel.send("使い方: !voicelang 自動/英→日/日→英" + '\u200B')

    async def _cmd_voicelang2(self, message, args: str) -> None:
        """!voicelang2 [自動|英→日|日→英|off] — 音声チャット翻訳言語2を設定（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        arg = args.strip()
        config = load_config()
        if not arg:
            current = config.get("voice_chat_lang_2", "") or "off"
            await message.channel.send(f"音声チャット言語2: {current} (使い方: !voicelang2 自動/英→日/日→英/off)" + '\u200B')
            return
        if arg == "off":
            config["voice_chat_lang_2"] = ""
            save_config(config)
            await message.channel.send("音声チャット言語2を無効にしました" + '\u200B')
        elif arg in VALID_TRANSLATE_MODES:
            config["voice_chat_lang_2"] = arg
            save_config(config)
            await message.channel.send(f"音声チャット言語2を {arg} に設定しました" + '\u200B')
        else:
            await message.channel.send("使い方: !voicelang2 自動/英→日/日→英/off" + '\u200B')

    async def _cmd_dict(self, message, args: str) -> None:
        """!dict — TTS辞書管理コマンド（モデレーター以上）

        !dict add <単語> <読み>  - 単語を追加
        !dict list               - 登録済み一覧を表示
        !dict remove <単語>      - 単語を削除
        """
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が必要です" + '\u200B')
            return

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "add":
            await self._cmd_dict_add(message, sub_args)
        elif subcmd == "list":
            await self._cmd_dict_list(message)
        elif subcmd == "remove":
            await self._cmd_dict_remove(message, sub_args)
        else:
            await message.channel.send(
                "使い方: !dict add <単語> <読み> | !dict list | !dict remove <単語>" + '\u200B'
            )

    async def _cmd_dict_add(self, message, args: str) -> None:
        """!dict add <単語> <読み> — TTS辞書に単語を追加"""
        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2:
            await message.channel.send("使い方: !dict add <単語> <読み>" + '\u200B')
            return

        word, reading = parts[0].strip(), parts[1].strip()
        if not word or not reading:
            await message.channel.send("使い方: !dict add <単語> <読み>" + '\u200B')
            return

        dictionary = get_dictionary()
        success = dictionary.add_word(word, reading)
        if success:
            await message.channel.send(f"辞書に追加しました: {word} → {reading}" + '\u200B')
        else:
            await message.channel.send("辞書への追加に失敗しました" + '\u200B')

    async def _cmd_dict_list(self, message) -> None:
        """!dict list — 登録済み辞書エントリを一覧表示"""
        dictionary = get_dictionary()
        entries = dictionary.get_all_entries()
        if not entries:
            await message.channel.send("辞書は空です" + '\u200B')
            return

        items = [f"{w}→{r}" for w, r in sorted(entries)]
        display = ", ".join(items[:10])
        remaining = len(items) - 10
        msg = f"辞書({len(items)}件): {display}"
        if remaining > 0:
            msg += f" ...他{remaining}件"
        await message.channel.send(msg + '\u200B')

    async def _cmd_dict_remove(self, message, args: str) -> None:
        """!dict remove <単語> — TTS辞書から単語を削除"""
        word = args.strip()
        if not word:
            await message.channel.send("使い方: !dict remove <単語>" + '\u200B')
            return

        dictionary = get_dictionary()
        success = dictionary.remove_word(word)
        if success:
            await message.channel.send(f"辞書から削除しました: {word}" + '\u200B')
        else:
            await message.channel.send(f"辞書に「{word}」は登録されていません" + '\u200B')

    async def _cmd_voice(self, message, args: str) -> None:
        """!voice — ボイス管理コマンド (MOD+)

        !voice list           - 利用可能なボイス一覧
        !voice set @user <ID> - ユーザーにボイスを割り当て
        !voice remove @user   - ボイス割り当てを解除
        !voice check @user    - ユーザーのボイスを確認
        """
        config = load_config()
        mode = config.get("voice_assign_mode", "mod_only")
        if mode == "disabled":
            await message.channel.send("ボイス割り当て機能は無効です" + '\u200B')
            return

        parts = args.strip().split()

        if not parts:
            await message.channel.send(
                "使い方: !voice list | set @user <ID> | remove @user | check @user"
                + '\u200B'
            )
            return

        subcmd = parts[0].lower()

        if subcmd == "list":
            await self._cmd_voice_list(message, config)
        elif subcmd == "set":
            await self._cmd_voice_set(message, parts[1:], config)
        elif subcmd == "remove":
            await self._cmd_voice_remove(message, parts[1:])
        elif subcmd == "check":
            await self._cmd_voice_check(message, parts[1:])
        else:
            await message.channel.send(
                "使い方: !voice list | set @user <ID> | remove @user | check @user"
                + '\u200B'
            )

    async def _cmd_voice_list(self, message, config: dict) -> None:
        """利用可能なボイス一覧を表示"""
        speakers = self.tts.get_speakers_list()
        if not speakers:
            await message.channel.send("ボイス一覧を取得できませんでした" + '\u200B')
            return

        allowed = config.get("voice_allowed_speakers", [])
        if allowed:
            speakers = [s for s in speakers if s["id"] in allowed]

        display_list = [f"{s['name']}({s['id']})" for s in speakers[:10]]
        remaining = len(speakers) - 10

        msg = f"ボイス: {', '.join(display_list)}"
        if remaining > 0:
            msg += f" ...他{remaining}件"

        await message.channel.send(msg + '\u200B')

    async def _cmd_voice_set(self, message, parts: list[str], config: dict) -> None:
        """!voice set @user <ID> — ユーザーにボイスを割り当て (MOD+)"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が必要です" + '\u200B')
            return

        if len(parts) < 2:
            await message.channel.send("使い方: !voice set @ユーザー名 <ボイスID>" + '\u200B')
            return

        target = parts[0].lstrip("@").lower()
        try:
            speaker_id = int(parts[1])
        except ValueError:
            await message.channel.send("ボイスIDは数値で指定してください" + '\u200B')
            return

        allowed = config.get("voice_allowed_speakers", [])
        if allowed and speaker_id not in allowed:
            await message.channel.send("このボイスIDは許可されていません" + '\u200B')
            return

        speaker_name = self._get_speaker_name(speaker_id)
        if not speaker_name:
            await message.channel.send(f"ボイスID {speaker_id} が見つかりません" + '\u200B')
            return

        assigner = getattr(message.author, "display_name", message.author.name)
        self._viewer_store.assign_voice(target, speaker_id, speaker_name, assigner)
        await message.channel.send(
            f"@{target} のボイスを {speaker_name} (ID:{speaker_id}) に設定しました"
            + '\u200B'
        )

    async def _cmd_voice_remove(self, message, parts: list[str]) -> None:
        """!voice remove @user — ボイス割り当てを解除 (MOD+)"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が必要です" + '\u200B')
            return

        if not parts:
            await message.channel.send("使い方: !voice remove @ユーザー名" + '\u200B')
            return

        target = parts[0].lstrip("@").lower()
        if self._viewer_store.remove_voice(target):
            await message.channel.send(f"@{target} のボイス割り当てを解除しました" + '\u200B')
        else:
            await message.channel.send(f"@{target} にはボイスが割り当てられていません" + '\u200B')

    async def _cmd_voice_check(self, message, parts: list[str]) -> None:
        """!voice check @user — ユーザーのボイスを確認 (MOD+)"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が必要です" + '\u200B')
            return

        if not parts:
            await message.channel.send("使い方: !voice check @ユーザー名" + '\u200B')
            return

        target = parts[0].lstrip("@").lower()
        viewer = self._viewer_store.get_viewer(target)
        if viewer and viewer.assigned_voice:
            voice = viewer.assigned_voice
            await message.channel.send(
                f"@{target}: {voice['speaker_name']} (ID:{voice['speaker_id']}) "
                f"視聴{viewer.visit_count}回" + '\u200B'
            )
        else:
            visit_count = self._viewer_store.get_visit_count(target)
            await message.channel.send(
                f"@{target}: ボイス未設定 / 視聴{visit_count}回" + '\u200B'
            )

    def _get_speaker_name(self, speaker_id: int) -> str | None:
        """VOICEVOX のスピーカー名を ID から取得する"""
        speakers = self.tts.get_speakers_list()
        for s in speakers:
            if s.get("id") == speaker_id:
                return s.get("display", s.get("name", f"Speaker {speaker_id}"))
        return None

    async def _cmd_myvoice(self, message, args: str) -> None:
        """!myvoice [ID] — 自分のボイスを設定/確認"""
        config = load_config()
        mode = config.get("voice_assign_mode", "mod_only")

        if mode == "disabled":
            await message.channel.send("ボイス割り当て機能は無効です" + '\u200B')
            return

        username = message.author.name
        display_name = getattr(message.author, "display_name", username)

        if not args.strip():
            # 現在のボイスを表示
            viewer = self._viewer_store.get_viewer(username)
            if viewer and viewer.assigned_voice:
                voice = viewer.assigned_voice
                await message.channel.send(
                    f"{display_name} のボイス: {voice['speaker_name']} (ID:{voice['speaker_id']})"
                    + '\u200B'
                )
            else:
                await message.channel.send(
                    f"{display_name}: ボイス未設定（デフォルト）" + '\u200B'
                )
            return

        # セルフ設定
        if mode != "self_service":
            # mod_only の場合でも MOD+ ならセルフ設定可能
            if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
                await message.channel.send(
                    "セルフボイス設定は無効です（モデレーターに依頼してください）" + '\u200B'
                )
                return

        # self_service モードの場合: 視聴回数チェック
        if mode == "self_service":
            min_visits = config.get("voice_self_assign_min_visits", 5)
            visit_count = self._viewer_store.get_visit_count(username)
            if visit_count < min_visits:
                await message.channel.send(
                    f"ボイス設定には{min_visits}回以上の視聴が必要です"
                    f"（現在: {visit_count}回）" + '\u200B'
                )
                return

        # ボイス ID のパース
        arg = args.strip()
        if arg.lower() == "reset":
            if self._viewer_store.remove_voice(username):
                await message.channel.send("ボイスをデフォルトに戻しました" + '\u200B')
            else:
                await message.channel.send("ボイスは既にデフォルトです" + '\u200B')
            return

        try:
            speaker_id = int(arg)
        except ValueError:
            await message.channel.send(
                "使い方: !myvoice <ボイスID> または !myvoice reset" + '\u200B'
            )
            return

        allowed = config.get("voice_allowed_speakers", [])
        if allowed and speaker_id not in allowed:
            await message.channel.send("このボイスIDは許可されていません" + '\u200B')
            return

        speaker_name = self._get_speaker_name(speaker_id)
        if not speaker_name:
            await message.channel.send(
                f"ボイスID {speaker_id} が見つかりません（!voice list で確認）" + '\u200B'
            )
            return

        self._viewer_store.assign_voice(username, speaker_id, speaker_name, display_name)
        await message.channel.send(
            f"ボイスを {speaker_name} に設定しました" + '\u200B'
        )

    async def _cmd_visits(self, message, args: str) -> None:
        """!visits [@user] — 視聴回数を確認"""
        if args.strip():
            # 他のユーザーの確認（MOD+ のみ）
            if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
                await message.channel.send(
                    "他のユーザーの確認はモデレーター以上が必要です" + '\u200B'
                )
                return
            target = args.strip().lstrip("@").lower()
            count = self._viewer_store.get_visit_count(target)
            await message.channel.send(f"@{target} の視聴回数: {count}回" + '\u200B')
        else:
            display_name = (
                getattr(message.author, "display_name", None) or message.author.name
            )
            count = self._viewer_store.get_visit_count(message.author.name)
            await message.channel.send(
                f"{display_name} の視聴回数: {count}回" + '\u200B'
            )

    @property
    def command_store(self) -> CommandStore:
        """GUIからカスタムコマンドストアにアクセスするためのプロパティ"""
        return self._command_store

    def set_commands_enabled(self, enabled: bool) -> None:
        """コマンド機能の有効/無効を切り替える"""
        self._commands_enabled = enabled
        logger.info("コマンド機能: %s", "有効" if enabled else "無効")

    # ------------------------------------------------------------------
    # 参加者管理コマンド
    # ------------------------------------------------------------------

    async def _cmd_remove(self, message, args: str) -> None:
        """!remove <username> — 参加者を待機リストから削除（モデレーター限定）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        username = args.strip().lstrip("@")
        if not username:
            await message.channel.send("使い方: !remove <ユーザー名>" + '\u200B')
            return
        success = self.tracker.remove_participant(username)
        if success:
            await message.channel.send(f"@{username} を参加者リストから削除しました" + '\u200B')
            if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                self.gui.refresh_participant_list()
        else:
            await message.channel.send(f"@{username} は参加者リストに見つかりません" + '\u200B')

    async def _cmd_clearall(self, message, args: str) -> None:
        """!clearall — 待機参加者リストを全件クリア（モデレーター限定）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        count = self.tracker.get_count()
        self.tracker.clear()
        await message.channel.send(f"参加者リストをクリアしました（{count}人）" + '\u200B')
        if self.gui and hasattr(self.gui, 'refresh_participant_list'):
            self.gui.refresh_participant_list()

    async def _cmd_nextround(self, message, args: str) -> None:
        """!nextround — 現在の待機者を参加済みに移動しリストをクリア（モデレーター限定）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        count = self.tracker.get_count()
        self.tracker.mark_all_as_participated()
        participated_total = self.tracker.get_participated_count()
        await message.channel.send(
            f"ラウンド開始: {count}人を参加済みに移動しました（累計参加済み: {participated_total}人）" + '\u200B'
        )
        if self.gui and hasattr(self.gui, 'refresh_participant_list'):
            self.gui.refresh_participant_list()

    async def _cmd_roundreset(self, message, args: str) -> None:
        """!roundreset — 参加済みセットをリセットし全員再参加可能にする（モデレーター限定）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        count = self.tracker.get_participated_count()
        self.tracker.reset_participated()
        await message.channel.send(
            f"ラウンドリセット: {count}人が再参加可能になりました" + '\u200B'
        )
        if self.gui and hasattr(self.gui, 'refresh_participant_list'):
            self.gui.refresh_participant_list()

    async def _cmd_leave(self, message, args: str) -> None:
        """!leave — 自分自身を待機リストから削除（全ユーザー）"""
        participant_name = getattr(message.author, "display_name", None) or message.author.name
        success = self.tracker.remove_participant(participant_name)
        if success:
            await message.channel.send(f"@{participant_name} 参加リストから退出しました" + '\u200B')
            if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                self.gui.refresh_participant_list()
        else:
            await message.channel.send(f"@{participant_name} 参加リストに登録されていません" + '\u200B')

    async def _cmd_played(self, message, args: str) -> None:
        """!played <username> — 指定ユーザーを参加済みにマーク（待機リストから除去）（モデレーター限定）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        username = args.strip().lstrip("@")
        if not username:
            await message.channel.send("使い方: !played <ユーザー名>" + '\u200B')
            return
        self.tracker.mark_as_participated(username)
        participated_count = self.tracker.get_participated_count()
        await message.channel.send(
            f"@{username} を参加済みにしました（参加済み累計: {participated_count}人）" + '\u200B'
        )
        if self.gui and hasattr(self.gui, 'refresh_participant_list'):
            self.gui.refresh_participant_list()

    async def _cmd_queue(self, message, args: str) -> None:
        """!queue <subcmd> [...] — 待機列の管理（モデレーター限定）

        !queue remove <ユーザー名>  — 待機リストから削除
        !queue clear               — 待機リストを全件クリア
        !queue next                — 待機者全員を参加済みに移動してリストをクリア
        !queue reset               — 参加済みセットをリセット（全員再参加可能に）
        !queue played <ユーザー名>  — 指定ユーザーを参加済みにマーク
        """
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "remove":
            username = sub_args.strip().lstrip("@")
            if not username:
                await message.channel.send("使い方: !queue remove <ユーザー名>" + '\u200B')
                return
            success = self.tracker.remove_participant(username)
            if success:
                await message.channel.send(f"@{username} を参加者リストから削除しました" + '\u200B')
                if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                    self.gui.refresh_participant_list()
            else:
                await message.channel.send(f"@{username} は参加者リストに見つかりません" + '\u200B')

        elif subcmd == "clear":
            count = self.tracker.get_count()
            self.tracker.clear()
            await message.channel.send(f"参加者リストをクリアしました（{count}人）" + '\u200B')
            if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                self.gui.refresh_participant_list()

        elif subcmd == "next":
            count = self.tracker.get_count()
            self.tracker.mark_all_as_participated()
            participated_total = self.tracker.get_participated_count()
            await message.channel.send(
                f"ラウンド開始: {count}人を参加済みに移動しました（累計参加済み: {participated_total}人）" + '\u200B'
            )
            if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                self.gui.refresh_participant_list()

        elif subcmd == "reset":
            count = self.tracker.get_participated_count()
            self.tracker.reset_participated()
            await message.channel.send(
                f"ラウンドリセット: {count}人が再参加可能になりました" + '\u200B'
            )
            if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                self.gui.refresh_participant_list()

        elif subcmd == "played":
            username = sub_args.strip().lstrip("@")
            if not username:
                await message.channel.send("使い方: !queue played <ユーザー名>" + '\u200B')
                return
            self.tracker.mark_as_participated(username)
            participated_count = self.tracker.get_participated_count()
            await message.channel.send(
                f"@{username} を参加済みにしました（参加済み累計: {participated_count}人）" + '\u200B'
            )
            if self.gui and hasattr(self.gui, 'refresh_participant_list'):
                self.gui.refresh_participant_list()

        else:
            await message.channel.send(
                "使い方: !queue remove <user> | clear | next | reset | played <user>" + '\u200B'
            )

    async def _cmd_stream(self, message, args: str) -> None:
        """!stream title/game [...] — 配信タイトル・ゲームカテゴリ変更（モデレーター限定、Twitch限定）

        !stream title <タイトル>  — 配信タイトルを変更
        !stream game <ゲーム名>   — ゲームカテゴリを変更
        """
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        value = parts[1].strip() if len(parts) > 1 else ""

        if not subcmd or not value:
            await message.channel.send(
                "使い方: !stream title <タイトル> | !stream game <ゲーム名>" + '\u200B'
            )
            return

        token = self.token
        client_id = self.client_id or ""
        broadcaster_id = None
        if self._eventsub_handler:
            broadcaster_id = getattr(self._eventsub_handler, '_broadcaster_id', None)

        if not broadcaster_id:
            await message.channel.send("配信者IDを取得できませんでした（Twitch接続を確認してください）" + '\u200B')
            return

        if subcmd == "title":
            success, msg = update_channel_info(token, client_id, broadcaster_id, title=value)
            if success:
                await message.channel.send(f"配信タイトルを変更しました: {value}" + '\u200B')
            else:
                await message.channel.send(f"タイトル変更に失敗しました: {msg}" + '\u200B')

        elif subcmd == "game":
            game_id, game_name = await asyncio.to_thread(search_game, token, client_id, value)
            if not game_id:
                await message.channel.send(f"ゲーム「{value}」が見つかりませんでした" + '\u200B')
                return
            success, msg = await asyncio.to_thread(
                update_channel_info, token, client_id, broadcaster_id, game_id=game_id
            )
            if success:
                await message.channel.send(f"ゲームカテゴリを変更しました: {game_name}" + '\u200B')
            else:
                await message.channel.send(f"ゲーム変更に失敗しました: {msg}" + '\u200B')

        else:
            await message.channel.send(
                "使い方: !stream title <タイトル> | !stream game <ゲーム名>" + '\u200B'
            )

    # ===== Game Commands =====

    async def _cmd_fortune(self, message, args: str) -> None:
        """!fortune — おみくじを引く"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("fortune", user, 30, 30)
        if not allowed:
            return
        self._cooldown_manager.record("fortune", user)
        result = fortune()
        await message.channel.send(f"@{message.author.display_name} {result}" + '\u200B')

    async def _cmd_dice(self, message, args: str) -> None:
        """!dice [XdY] — サイコロを振る"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("dice", user, 5, 5)
        if not allowed:
            return
        self._cooldown_manager.record("dice", user)
        result = roll_dice(args.strip() or "1d6")
        await message.channel.send(f"@{message.author.display_name} {result}" + '\u200B')

    async def _cmd_coin(self, message, args: str) -> None:
        """!coin — コインを投げる"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("coin", user, 5, 5)
        if not allowed:
            return
        self._cooldown_manager.record("coin", user)
        result = coin_toss()
        await message.channel.send(f"@{message.author.display_name} {result}" + '\u200B')

    async def _cmd_slot(self, message, args: str) -> None:
        """!slot — スロットを回す"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("slot", user, 10, 10)
        if not allowed:
            return
        self._cooldown_manager.record("slot", user)
        result = spin_slot()
        await message.channel.send(f"@{message.author.display_name} {result}" + '\u200B')
        if self.tts_enabled_getter():
            self.tts.speak(result)

    async def _cmd_roulette(self, message, args: str) -> None:
        """!roulette [option1 option2 ...] — ルーレットを回す"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("roulette", user, 10, 10)
        if not allowed:
            return
        self._cooldown_manager.record("roulette", user)
        options = [o for o in args.split() if o] if args.strip() else []
        result = spin_roulette(options)
        await message.channel.send(f"@{message.author.display_name} {result}" + '\u200B')

    async def _cmd_janken(self, message, args: str) -> None:
        """!janken <グー/チョキ/パー> — じゃんけんをする"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("janken", user, 5, 5)
        if not allowed:
            return
        self._cooldown_manager.record("janken", user)
        result = play_janken(args)
        await message.channel.send(f"@{message.author.display_name} {result}" + '\u200B')

    async def _cmd_startguess(self, message, args: str) -> None:
        """!startguess [min] [max] — 数字当てゲームを開始（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        parts = args.split()
        try:
            min_val = int(parts[0]) if len(parts) > 0 else 1
            max_val = int(parts[1]) if len(parts) > 1 else 100
        except ValueError:
            await message.channel.send("使い方: !startguess [最小値] [最大値]" + '\u200B')
            return
        result = get_number_guess_game().start(message.author.name.lower(), min_val, max_val)
        await message.channel.send(result + '\u200B')

    async def _cmd_guess(self, message, args: str) -> None:
        """!guess <number> — 数字当てゲームに参加"""
        user = message.author.name.lower()
        allowed, _ = self._cooldown_manager.check("guess", user, 3, 3)
        if not allowed:
            return
        self._cooldown_manager.record("guess", user)
        result = get_number_guess_game().guess(message.author.display_name, args.strip())
        await message.channel.send(result + '\u200B')

    async def _cmd_endguess(self, message, args: str) -> None:
        """!endguess — 数字当てゲームを終了（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        result = get_number_guess_game().end()
        await message.channel.send(result + '\u200B')

    async def _cmd_giveaway(self, message, args: str) -> None:
        """!giveaway start/draw/end — 抽選管理（モデレーター以上）"""
        if not check_permission(message.author, PermissionLevel.MODERATOR, self.channel_name):
            await message.channel.send("このコマンドはモデレーター以上が使用できます" + '\u200B')
            return
        gm = get_giveaway_manager()
        sub_cmd = args.strip().lower()
        if sub_cmd == "start":
            result = gm.start(message.author.name.lower())
        elif sub_cmd == "draw":
            result = gm.draw()
        elif sub_cmd == "end":
            result = gm.end()
        else:
            result = "使い方: !giveaway start / !giveaway draw / !giveaway end"
        await message.channel.send(result + '\u200B')

    async def _cmd_enter(self, message, args: str) -> None:
        """!enter — 抽選に参加する"""
        gm = get_giveaway_manager()
        is_sub = getattr(message.author, 'is_subscriber', False)
        result = gm.enter(
            message.author.name.lower(),
            message.author.display_name,
            bool(is_sub),
        )
        await message.channel.send(result + '\u200B')

    async def event_raw_usernotice(self, channel, tags: dict):
        """サブスクやギフトなどのUSERNOTICEイベントを処理（twitchio 2.x準拠）"""
        msg_id = tags.get("msg-id") if tags else None

        # 自分でサブスク登録（sub, resub, primepaidupgrade）
        self_sub_types = {"sub", "resub", "primepaidupgrade"}
        # ギフトサブ関連
        gift_sub_types = {
            "subgift",
            "anonsubgift",
            "submysterygift",
            "anonsubmysterygift",
            "giftpaidupgrade",
            "rewardgift",
            "communitypayforward",
        }
        # その他（bitsbadgetierなど）
        other_sub_types = {"bitsbadgetier"}

        all_sub_related = self_sub_types | gift_sub_types | other_sub_types
        if msg_id not in all_sub_related:
            return

        display_name = tags.get("display-name") or tags.get("login") or "匿名"

        system_msg = ""
        if tags.get("system-msg"):
            system_msg = self._decode_irc_tag(tags.get("system-msg"))

        # イベントタイプを判別
        if msg_id in self_sub_types:
            fallback_msg = f"{display_name} がサブスク登録しました"
            event_type = "subscription"
        elif msg_id in gift_sub_types:
            fallback_msg = f"{display_name} がギフトサブを贈りました"
            event_type = "gift_sub"
        else:
            fallback_msg = f"{display_name} がサブスクしました"
            event_type = "subscription"

        event_msg = system_msg if system_msg else fallback_msg
        self._notify_special_event(event_msg, event_type=event_type)

    def _notify_special_event(self, message: str, event_type: str = "other"):
        """GUIの特別イベントログに通知"""
        if hasattr(self, "gui") and self.gui and hasattr(self.gui, "log_special_event"):
            try:
                self.gui.log_special_event(message, event_type)
            except Exception as e:
                logger.error(f"Failed to notify special event: {e}", exc_info=True)

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

    async def send_participant_list(self):
        """参加者リストをチャットに送信"""
        if not self.tracker or not hasattr(self, '_connection') or not self._connection:
            logger.warning("BOTが接続されていないため、参加者リストを送信できません")
            return False

        participants = self.tracker.get_participant_names()

        if not participants:
            message = "【待機参加者リスト】参加者はいません"
        else:
            participant_str = "→".join(participants)
            message = f"【待機参加者リスト】{participant_str}"

        try:
            # 最初のチャンネルに送信
            if self._connection and self._connection.connected_channels:
                channel = self._connection.connected_channels[0]
                await channel.send(message)
                logger.info(f"参加者リストを送信: {message}")
                return True
        except Exception as e:
            logger.error(f"参加者リスト送信エラー: {e}", exc_info=True)
            return False

    def stop(self):
        """
        BOTを安全に停止する
        """
        logger.info("Bot.stop() called")

        # 停止フラグを設定（二重処理防止）
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

        # ループが存在しない場合は何もしない
        if loop is None:
            logger.info("No running loop, nothing to stop.")
            self._processed_message_ids.clear()
            return

        # ループを停止
        try:
            if loop.is_running():
                # 別スレッドからループを停止
                loop.call_soon_threadsafe(loop.stop)
                logger.info("Bot loop stop requested.")
        except Exception as e:
            logger.warning(f"Exception during loop stop: {e}")

        # クリーンアップ
        self._running_loop = None
        self._processed_message_ids.clear()
        # セッションアーカイブを終了
        if self._archive:
            try:
                self._archive.end_session()
                self._archive.close()
            except Exception as e:
                logger.warning(f"Exception closing session archive: {e}")
        # プラグインを停止
        try:
            self._plugin_manager.unload_all()
        except Exception as e:
            logger.warning(f"Exception unloading plugins: {e}")
        logger.info("Bot.stop() completed")
