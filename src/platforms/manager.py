"""
マルチプラットフォームマネージャー

複数のプラットフォーム（Twitch, YouTube等）を同時に管理する。
"""

import asyncio
from typing import Optional, Callable, List, Dict, Any

from src.platforms.base import PlatformAdapter, PlatformType, SpecialEvent
from src.platforms.twitch import TwitchAdapter
from src.platforms.youtube import YouTubeAdapter
from src.comment_data import CommentData
from src.logger import logger
from src.config import load_config


class MultiPlatformManager:
    """
    マルチプラットフォームマネージャー

    複数のプラットフォームアダプターを管理し、同時接続をサポートする。
    """

    def __init__(
        self,
        deepl_api_key: str,
        get_lang_mode: Callable[[], str],
        tts_enabled_getter: Callable[[], bool],
        tts_include_name_getter: Callable[[], bool],
        gui_ref: Any = None,
    ):
        self._deepl_api_key = deepl_api_key
        self._get_lang_mode = get_lang_mode
        self._tts_enabled_getter = tts_enabled_getter
        self._tts_include_name_getter = tts_include_name_getter
        self._gui = gui_ref

        self._adapters: Dict[PlatformType, PlatformAdapter] = {}
        self._message_callback: Optional[Callable[[CommentData], None]] = None
        self._event_callback: Optional[Callable[[SpecialEvent], None]] = None

    @property
    def connected_platforms(self) -> List[PlatformType]:
        """接続中のプラットフォーム一覧"""
        return [
            platform_type
            for platform_type, adapter in self._adapters.items()
            if adapter.is_connected
        ]

    @property
    def is_any_connected(self) -> bool:
        """いずれかのプラットフォームに接続中か"""
        return len(self.connected_platforms) > 0

    def set_message_callback(self, callback: Callable[[CommentData], None]) -> None:
        """メッセージ受信時のコールバックを設定"""
        self._message_callback = callback
        for adapter in self._adapters.values():
            adapter.set_message_callback(callback)

    def set_event_callback(self, callback: Callable[[SpecialEvent], None]) -> None:
        """特別イベント受信時のコールバックを設定"""
        self._event_callback = callback
        for adapter in self._adapters.values():
            adapter.set_event_callback(callback)

    def get_adapter(self, platform_type: PlatformType) -> Optional[PlatformAdapter]:
        """指定したプラットフォームのアダプターを取得"""
        return self._adapters.get(platform_type)

    def get_twitch_adapter(self) -> Optional[TwitchAdapter]:
        """Twitchアダプターを取得"""
        adapter = self._adapters.get(PlatformType.TWITCH)
        return adapter if isinstance(adapter, TwitchAdapter) else None

    def get_youtube_adapter(self) -> Optional[YouTubeAdapter]:
        """YouTubeアダプターを取得"""
        adapter = self._adapters.get(PlatformType.YOUTUBE)
        return adapter if isinstance(adapter, YouTubeAdapter) else None

    async def connect_twitch(
        self,
        token: str,
        client_id: str,
        channel: str,
    ) -> bool:
        """Twitchに接続"""
        if PlatformType.TWITCH in self._adapters:
            await self.disconnect_twitch()

        adapter = TwitchAdapter(
            token=token,
            client_id=client_id,
            deepl_api_key=self._deepl_api_key,
            get_lang_mode=self._get_lang_mode,
            tts_enabled_getter=self._tts_enabled_getter,
            tts_include_name_getter=self._tts_include_name_getter,
            gui_ref=self._gui,
        )

        if self._message_callback:
            adapter.set_message_callback(self._message_callback)
        if self._event_callback:
            adapter.set_event_callback(self._event_callback)

        self._adapters[PlatformType.TWITCH] = adapter

        try:
            success = await adapter.connect(channel)
            if success:
                logger.info(f"Twitch connected: {channel}")
            else:
                logger.error(f"Twitch connection failed: {channel}")
                del self._adapters[PlatformType.TWITCH]
            return success
        except Exception as e:
            logger.error(f"Twitch connection error: {e}", exc_info=True)
            if PlatformType.TWITCH in self._adapters:
                del self._adapters[PlatformType.TWITCH]
            return False

    async def connect_youtube(
        self,
        access_token: str,
        refresh_token: Optional[str],
        client_id: str,
        client_secret: str,
        live_id: str,
    ) -> bool:
        """YouTubeに接続"""
        if PlatformType.YOUTUBE in self._adapters:
            await self.disconnect_youtube()

        adapter = YouTubeAdapter(
            access_token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            deepl_api_key=self._deepl_api_key,
            get_lang_mode=self._get_lang_mode,
            tts_enabled_getter=self._tts_enabled_getter,
            tts_include_name_getter=self._tts_include_name_getter,
            gui_ref=self._gui,
        )

        if self._message_callback:
            adapter.set_message_callback(self._message_callback)
        if self._event_callback:
            adapter.set_event_callback(self._event_callback)

        self._adapters[PlatformType.YOUTUBE] = adapter

        try:
            success = await adapter.connect(live_id)
            if success:
                logger.info(f"YouTube connected: {live_id}")
            else:
                logger.error(f"YouTube connection failed: {live_id}")
                del self._adapters[PlatformType.YOUTUBE]
            return success
        except Exception as e:
            logger.error(f"YouTube connection error: {e}", exc_info=True)
            if PlatformType.YOUTUBE in self._adapters:
                del self._adapters[PlatformType.YOUTUBE]
            return False

    async def connect_all(self) -> Dict[PlatformType, bool]:
        """設定されている全プラットフォームに接続"""
        config = load_config()
        results: Dict[PlatformType, bool] = {}

        # Twitch接続
        if config.get("twitch_enabled") and config.get("twitch_access_token"):
            twitch_success = await self.connect_twitch(
                token=config["twitch_access_token"],
                client_id=config.get("twitch_client_id", ""),
                channel=config.get("channel_name", ""),
            )
            results[PlatformType.TWITCH] = twitch_success

        # YouTube接続
        if config.get("youtube_enabled") and config.get("youtube_access_token"):
            youtube_success = await self.connect_youtube(
                access_token=config["youtube_access_token"],
                refresh_token=config.get("youtube_refresh_token"),
                client_id=config.get("youtube_client_id", ""),
                client_secret=config.get("youtube_client_secret", ""),
                live_id=config.get("youtube_live_id", ""),
            )
            results[PlatformType.YOUTUBE] = youtube_success

        return results

    async def disconnect_twitch(self) -> None:
        """Twitch接続を切断"""
        adapter = self._adapters.get(PlatformType.TWITCH)
        if adapter:
            await adapter.disconnect()
            del self._adapters[PlatformType.TWITCH]
            logger.info("Twitch disconnected")

    async def disconnect_youtube(self) -> None:
        """YouTube接続を切断"""
        adapter = self._adapters.get(PlatformType.YOUTUBE)
        if adapter:
            await adapter.disconnect()
            del self._adapters[PlatformType.YOUTUBE]
            logger.info("YouTube disconnected")

    async def disconnect_all(self) -> None:
        """全プラットフォームの接続を切断"""
        platforms = list(self._adapters.keys())
        for platform_type in platforms:
            adapter = self._adapters.get(platform_type)
            if adapter:
                try:
                    await adapter.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting {platform_type}: {e}")

        self._adapters.clear()
        logger.info("All platforms disconnected")

    async def send_message(
        self,
        message: str,
        platform: Optional[PlatformType] = None,
    ) -> Dict[PlatformType, bool]:
        """
        メッセージを送信

        Args:
            message: 送信するメッセージ
            platform: 送信先プラットフォーム（Noneの場合は全て）

        Returns:
            各プラットフォームの送信結果
        """
        results: Dict[PlatformType, bool] = {}

        if platform:
            adapter = self._adapters.get(platform)
            if adapter and adapter.is_connected:
                results[platform] = await adapter.send_message(message)
        else:
            for platform_type, adapter in self._adapters.items():
                if adapter.is_connected:
                    try:
                        results[platform_type] = await adapter.send_message(message)
                    except Exception as e:
                        logger.error(f"Send message error ({platform_type}): {e}")
                        results[platform_type] = False

        return results

    def stop_sync(self) -> None:
        """
        同期的に全アダプターを停止（GUIスレッドから呼び出し用）

        Note: Twitchアダプターには同期停止メソッドがある
        """
        twitch = self.get_twitch_adapter()
        if twitch and twitch.bot:
            twitch.bot.stop()

        # 他のアダプターはフラグを立てて停止を促す
        youtube = self.get_youtube_adapter()
        if youtube:
            youtube._stopped = True
