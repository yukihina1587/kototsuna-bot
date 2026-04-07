"""
VOICEVOX Engine プロセス管理モジュール
VOICEVOX Engineの起動・停止を管理
"""
import subprocess
import time
import os
import platform
import requests
from typing import Optional
from src.logger import logger


class VoicevoxEngineManager:
    """VOICEVOX Engineのプロセス管理"""

    def __init__(self, engine_path: str = "", api_url: str = "http://localhost:50021"):
        """
        Initialize VOICEVOX Engine Manager

        Args:
            engine_path: VOICEVOX Engineの実行ファイルパス
            api_url: VOICEVOX API URL
        """
        self.engine_path = engine_path
        self.api_url = api_url
        self.process: Optional[subprocess.Popen] = None
        self.is_managed_by_us = False  # このアプリが起動したプロセスかどうか

    def is_running(self) -> bool:
        """
        VOICEVOX Engineが起動しているかチェック

        Returns:
            起動している場合True
        """
        try:
            response = requests.get(f"{self.api_url}/version", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def start(self) -> bool:
        """
        VOICEVOX Engineを起動

        Returns:
            起動成功した場合True
        """
        # 既に起動している場合
        if self.is_running():
            logger.info("VOICEVOX Engine is already running")
            return True

        # 実行ファイルパスが設定されていない場合
        if not self.engine_path:
            logger.error("❌ VOICEVOX Engine path is not configured")
            logger.error("設定タブで「VOICEVOX Engineパス」を正しく設定してください")
            return False

        # パスの正規化と絶対パス化
        # os.path.normpath: スラッシュを正規化、余分な区切り文字を削除
        # os.path.abspath: 絶対パスに変換
        normalized_path = os.path.normpath(self.engine_path)
        abs_path = os.path.abspath(normalized_path)

        logger.debug(f"パス正規化: {self.engine_path} → {normalized_path} → {abs_path}")

        # ファイルが存在しない場合
        if not os.path.exists(abs_path):
            logger.error(f"❌ VOICEVOX Engine executable not found at: {abs_path}")
            logger.error(f"設定されたパス: {self.engine_path}")
            logger.error(f"正規化後: {normalized_path}")

            # パス形式のヒント
            if platform.system() == "Windows":
                logger.error("正しい形式の例: C:\\Program Files\\VOICEVOX\\run.exe または E:\\VOICEVOX\\run.exe")

            logger.error("「参照...」ボタンを使って正しい実行ファイル（run.exe）を選択してください")
            return False

        # ファイルタイプの検証（Windowsの場合）
        if platform.system() == "Windows" and not abs_path.lower().endswith('.exe'):
            logger.warning(f"⚠️ ファイルが .exe で終わっていません: {abs_path}")
            logger.warning("正しいファイルを選択しているか確認してください")

        # パスを絶対パスに更新
        self.engine_path = abs_path
        logger.info(f"VOICEVOX Engine パス確定: {abs_path}")

        try:
            logger.info(f"Starting VOICEVOX Engine: {self.engine_path}")

            # プラットフォームに応じた起動方法
            system = platform.system()

            if system == "Windows":
                # Windowsの場合、バックグラウンドで起動
                # CREATE_NO_WINDOW フラグを使用してウィンドウを非表示に
                CREATE_NO_WINDOW = 0x08000000
                self.process = subprocess.Popen(
                    [self.engine_path],
                    creationflags=CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                # Linux/Macの場合
                self.process = subprocess.Popen(
                    [self.engine_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

            self.is_managed_by_us = True
            logger.info(f"VOICEVOX Engine process started (PID: {self.process.pid})")

            # 起動を待機（最大30秒）
            # PCスペックによっては起動に時間がかかるため長めに設定
            for i in range(60):  # 0.5秒 × 60 = 30秒
                time.sleep(0.5)
                if self.is_running():
                    logger.info(f"✅ VOICEVOX Engine is ready (took {(i+1)*0.5:.1f}s)")
                    return True

            logger.warning("VOICEVOX Engine started but API is not responding (timeout)")
            return False

        except Exception as e:
            logger.error(f"Failed to start VOICEVOX Engine: {e}", exc_info=True)
            return False

    def stop(self):
        """VOICEVOX Engineを停止（このアプリが起動したプロセスのみ）"""
        if self.process and self.is_managed_by_us:
            try:
                logger.info("Stopping VOICEVOX Engine...")
                self.process.terminate()

                # 終了を待つ（最大5秒）
                try:
                    self.process.wait(timeout=5)
                    logger.info("VOICEVOX Engine stopped gracefully")
                except subprocess.TimeoutExpired:
                    # 強制終了
                    logger.warning("VOICEVOX Engine did not stop gracefully, killing...")
                    self.process.kill()
                    self.process.wait()
                    logger.info("VOICEVOX Engine killed")

                self.process = None
                self.is_managed_by_us = False

            except Exception as e:
                logger.error(f"Error stopping VOICEVOX Engine: {e}", exc_info=True)
        else:
            logger.debug("VOICEVOX Engine was not started by this app, not stopping")

    def __del__(self):
        """デストラクタ: プロセスをクリーンアップ"""
        self.stop()


# グローバルインスタンス
_manager_instance: Optional[VoicevoxEngineManager] = None


def get_voicevox_manager(engine_path: str = "", api_url: str = "http://localhost:50021") -> VoicevoxEngineManager:
    """
    VOICEVOX Engine Managerのグローバルインスタンスを取得

    Args:
        engine_path: VOICEVOX Engineの実行ファイルパス
        api_url: VOICEVOX API URL

    Returns:
        VoicevoxEngineManagerインスタンス
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = VoicevoxEngineManager(engine_path, api_url)
    else:
        # パスが変更された場合は更新
        if engine_path and engine_path != _manager_instance.engine_path:
            _manager_instance.engine_path = engine_path
        if api_url and api_url != _manager_instance.api_url:
            _manager_instance.api_url = api_url
    return _manager_instance
