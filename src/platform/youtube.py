"""
YouTubeプラットフォームアダプター

YouTube Live Chat APIを使用してYouTube Liveチャットに接続する。
"""

import asyncio
from typing import Optional, Callable, Any, List
from datetime import datetime

from src.platform.base import PlatformAdapter, PlatformType, SpecialEvent, EventType
from src.translator import translate_text
from src.logger import logger
from src.tts import get_tts_instance, is_japanese
from src.comment_data import CommentData, Platform
from src.config import load_config

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    logger.warning("Google API client not installed. YouTube support disabled.")


def create_youtube_comment(
    username: str,
    message: str,
    display_name: Optional[str] = None,
    user_id: Optional[str] = None,
    profile_image_url: Optional[str] = None,
    is_member: bool = False,
    translated: Optional[str] = None,
) -> CommentData:
    """YouTubeコメントからCommentDataを作成"""
    return CommentData(
        platform=Platform.YOUTUBE,
        username=username,
        display_name=display_name or username,
        message=message,
        translated=translated,
        badges=[],
        is_subscriber=is_member,
        is_moderator=False,
        is_broadcaster=False,
        user_color=None,
        raw_data={
            "user_id": user_id,
            "profile_image_url": profile_image_url,
            "is_member": is_member,
        }
    )


class YouTubeAdapter(PlatformAdapter):
    """
    YouTubeプラットフォームアダプター

    YouTube Live Chat APIを使用してYouTube Liveチャットに接続し、
    メッセージの受信を行う。
    """

    # ポーリング間隔（ミリ秒）
    DEFAULT_POLLING_INTERVAL_MS = 5000
    MIN_POLLING_INTERVAL_MS = 1000

    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str],
        client_id: str,
        client_secret: str,
        deepl_api_key: str,
        get_lang_mode: Callable[[], str],
        tts_enabled_getter: Callable[[], bool],
        tts_include_name_getter: Callable[[], bool],
        gui_ref: Any = None,
    ):
        super().__init__()
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._deepl_api_key = deepl_api_key
        self._get_lang_mode = get_lang_mode
        self._tts_enabled_getter = tts_enabled_getter
        self._tts_include_name_getter = tts_include_name_getter
        self._gui = gui_ref
        self._tts = get_tts_instance()

        self._youtube_service = None
        self._live_chat_id: Optional[str] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._next_page_token: Optional[str] = None
        self._polling_interval_ms = self.DEFAULT_POLLING_INTERVAL_MS
        self._processed_message_ids: set[str] = set()
        self._stopped = False

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.YOUTUBE

    def _build_credentials(self) -> Optional[Credentials]:
        """Google API用の認証情報を構築"""
        if not GOOGLE_API_AVAILABLE:
            return None

        return Credentials(
            token=self._access_token,
            refresh_token=self._refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

    async def connect(self, channel: str, **kwargs) -> bool:
        """
        YouTube Liveチャットに接続

        Args:
            channel: ライブ配信ID または チャンネルID
        """
        if not GOOGLE_API_AVAILABLE:
            logger.error("Google API client not available")
            return False

        if self._connected:
            logger.warning("Already connected")
            return False

        self._channel = channel
        self._stopped = False

        try:
            # YouTube Data API サービスを構築
            credentials = self._build_credentials()
            if not credentials:
                logger.error("Failed to build credentials")
                return False

            self._youtube_service = build('youtube', 'v3', credentials=credentials)

            # Live Chat IDを取得
            self._live_chat_id = await self._get_live_chat_id(channel)
            if not self._live_chat_id:
                logger.error(f"Failed to get live chat ID for {channel}")
                return False

            logger.info(f"YouTube Live Chat ID: {self._live_chat_id}")

            # ポーリングタスクを開始
            self._polling_task = asyncio.create_task(self._poll_messages())
            self._connected = True
            logger.info(f"YouTubeAdapter connected to {channel}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to YouTube: {e}", exc_info=True)
            return False

    async def _get_live_chat_id(self, video_or_channel_id: str) -> Optional[str]:
        """
        ライブ配信のLive Chat IDを取得

        Args:
            video_or_channel_id: ライブ配信のビデオID または チャンネルID
        """
        try:
            # まずビデオIDとして試す
            response = self._youtube_service.videos().list(
                part="liveStreamingDetails",
                id=video_or_channel_id
            ).execute()

            if response.get("items"):
                live_chat_id = response["items"][0].get("liveStreamingDetails", {}).get("activeLiveChatId")
                if live_chat_id:
                    return live_chat_id

            # チャンネルIDとして、アクティブなライブ配信を検索
            response = self._youtube_service.search().list(
                part="id",
                channelId=video_or_channel_id,
                eventType="live",
                type="video",
                maxResults=1
            ).execute()

            if response.get("items"):
                video_id = response["items"][0]["id"]["videoId"]
                # 再度ビデオ情報を取得
                video_response = self._youtube_service.videos().list(
                    part="liveStreamingDetails",
                    id=video_id
                ).execute()

                if video_response.get("items"):
                    return video_response["items"][0].get("liveStreamingDetails", {}).get("activeLiveChatId")

        except Exception as e:
            logger.error(f"Failed to get live chat ID: {e}", exc_info=True)

        return None

    async def disconnect(self) -> None:
        """接続を切断"""
        self._stopped = True

        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None

        self._youtube_service = None
        self._live_chat_id = None
        self._connected = False
        self._channel = None
        self._processed_message_ids.clear()
        logger.info("YouTubeAdapter disconnected")

    async def send_message(self, message: str) -> bool:
        """
        チャットにメッセージを送信

        Note: YouTube Live Chat APIでのメッセージ送信には
        追加の権限とクォータが必要
        """
        if not self._youtube_service or not self._live_chat_id:
            logger.warning("Not connected, cannot send message")
            return False

        try:
            self._youtube_service.liveChatMessages().insert(
                part="snippet",
                body={
                    "snippet": {
                        "liveChatId": self._live_chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {
                            "messageText": message
                        }
                    }
                }
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return False

    async def _poll_messages(self) -> None:
        """チャットメッセージをポーリング"""
        logger.info("Starting YouTube chat polling...")

        while not self._stopped and self._connected:
            try:
                await self._fetch_messages()
                await asyncio.sleep(self._polling_interval_ms / 1000)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                await asyncio.sleep(5)  # エラー時は5秒待機

        logger.info("YouTube chat polling stopped")

    async def _fetch_messages(self) -> None:
        """メッセージを取得して処理"""
        if not self._youtube_service or not self._live_chat_id:
            return

        try:
            request_params = {
                "liveChatId": self._live_chat_id,
                "part": "snippet,authorDetails",
                "maxResults": 200,
            }

            if self._next_page_token:
                request_params["pageToken"] = self._next_page_token

            response = self._youtube_service.liveChatMessages().list(
                **request_params
            ).execute()

            # 次回のポーリング間隔を更新
            self._polling_interval_ms = max(
                response.get("pollingIntervalMillis", self.DEFAULT_POLLING_INTERVAL_MS),
                self.MIN_POLLING_INTERVAL_MS
            )
            self._next_page_token = response.get("nextPageToken")

            # メッセージを処理
            for item in response.get("items", []):
                await self._process_chat_item(item)

        except Exception as e:
            logger.error(f"Failed to fetch messages: {e}", exc_info=True)

    async def _process_chat_item(self, item: dict) -> None:
        """チャットアイテムを処理"""
        message_id = item.get("id")

        # 重複チェック
        if message_id in self._processed_message_ids:
            return
        self._processed_message_ids.add(message_id)

        # メモリ制限
        if len(self._processed_message_ids) > 1000:
            to_remove = list(self._processed_message_ids)[:500]
            for old_id in to_remove:
                self._processed_message_ids.discard(old_id)

        snippet = item.get("snippet", {})
        author_details = item.get("authorDetails", {})
        message_type = snippet.get("type")

        # 通常のテキストメッセージ
        if message_type == "textMessageEvent":
            await self._handle_text_message(snippet, author_details)

        # スーパーチャット
        elif message_type == "superChatEvent":
            await self._handle_super_chat(snippet, author_details)

        # スーパーステッカー
        elif message_type == "superStickerEvent":
            await self._handle_super_sticker(snippet, author_details)

        # 新規メンバー
        elif message_type == "newSponsorEvent":
            await self._handle_new_member(snippet, author_details)

        # メンバーシップギフト
        elif message_type == "membershipGiftingEvent":
            await self._handle_membership_gift(snippet, author_details)

    async def _handle_text_message(self, snippet: dict, author: dict) -> None:
        """テキストメッセージを処理"""
        message_text = snippet.get("textMessageDetails", {}).get("messageText", "")
        display_name = author.get("displayName", "")
        channel_id = author.get("channelId", "")
        profile_image = author.get("profileImageUrl", "")
        is_member = author.get("isChatSponsor", False)

        comment = create_youtube_comment(
            username=channel_id,
            message=message_text,
            display_name=display_name,
            user_id=channel_id,
            profile_image_url=profile_image,
            is_member=is_member,
        )

        # 翻訳処理
        await self._process_message(comment, message_text)

    async def _handle_super_chat(self, snippet: dict, author: dict) -> None:
        """スーパーチャットを処理"""
        super_chat_details = snippet.get("superChatDetails", {})
        amount_display = super_chat_details.get("amountDisplayString", "")
        amount_micros = super_chat_details.get("amountMicros", 0)
        currency = super_chat_details.get("currency", "JPY")
        user_comment = super_chat_details.get("userComment", "")
        display_name = author.get("displayName", "")

        message = f"{display_name} が {amount_display} のスーパーチャットを送りました"
        if user_comment:
            message += f"「{user_comment}」"

        event = SpecialEvent(
            event_type=EventType.SUPER_CHAT,
            message=message,
            user_name=display_name,
            amount=amount_micros // 1000000,  # マイクロ単位から通常単位へ
            currency=currency,
        )
        self._notify_event(event)

    async def _handle_super_sticker(self, snippet: dict, author: dict) -> None:
        """スーパーステッカーを処理"""
        sticker_details = snippet.get("superStickerDetails", {})
        amount_display = sticker_details.get("amountDisplayString", "")
        display_name = author.get("displayName", "")

        event = SpecialEvent(
            event_type=EventType.SUPER_CHAT,
            message=f"{display_name} が {amount_display} のスーパーステッカーを送りました",
            user_name=display_name,
        )
        self._notify_event(event)

    async def _handle_new_member(self, snippet: dict, author: dict) -> None:
        """新規メンバーを処理"""
        display_name = author.get("displayName", "")

        event = SpecialEvent(
            event_type=EventType.MEMBER,
            message=f"{display_name} さんがメンバーになりました",
            user_name=display_name,
        )
        self._notify_event(event)

    async def _handle_membership_gift(self, snippet: dict, author: dict) -> None:
        """メンバーシップギフトを処理"""
        gift_details = snippet.get("membershipGiftingDetails", {})
        gift_count = gift_details.get("giftMembershipsCount", 1)
        display_name = author.get("displayName", "")

        event = SpecialEvent(
            event_type=EventType.GIFT_SUB,
            message=f"{display_name} が {gift_count} 件のメンバーシップをギフトしました",
            user_name=display_name,
            amount=gift_count,
        )
        self._notify_event(event)

    async def _process_message(self, comment: CommentData, original_text: str) -> None:
        """メッセージを処理（翻訳・TTS・GUI通知）"""
        # 翻訳設定チェック
        config = load_config()
        if not config.get("chat_translation_enabled", False):
            self._notify_message(comment)
            self._speak_message(original_text, comment)
            return

        # 翻訳実行
        lang_mode = self._get_lang_mode()
        translated = await translate_text(original_text, lang_mode, self._deepl_api_key)

        if translated == "":
            if self._gui:
                self._gui.log_message("🚫 翻訳フィルタによりスキップしました", log_type="system")
            self._notify_message(comment)
            return

        # コメントデータを更新
        if translated and translated != original_text:
            comment.translated = translated

        self._notify_message(comment)
        self._speak_message(original_text, comment, translated)

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
