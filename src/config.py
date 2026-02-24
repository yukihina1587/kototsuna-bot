import json
import os
import re
import sys
from datetime import datetime
from src.logger import logger


def _get_config_dir() -> str:
    """config.json を格納するディレクトリを返す"""
    if getattr(sys, 'frozen', False):
        # PyInstaller exe: exeと同じフォルダ
        return os.path.dirname(os.path.abspath(sys.executable))
    # 開発環境: プロジェクトルート（src/ の親）
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _resolve_config_path() -> str:
    """config.json のパスを決定する（旧バージョンからの移行対応）"""
    config_dir = _get_config_dir()
    primary = os.path.join(config_dir, "config.json")

    # 正規の場所にあればそのまま使用
    if os.path.exists(primary):
        return primary

    # 旧バージョン（相対パス）で保存されたconfig.jsonをワーキングディレクトリから探す
    cwd_config = os.path.join(os.getcwd(), "config.json")
    if cwd_config != primary and os.path.exists(cwd_config):
        try:
            import shutil
            shutil.copy2(cwd_config, primary)
        except Exception:
            # コピー失敗時は旧パスを使い続ける
            return cwd_config

    return primary


CONFIG_FILE = _resolve_config_path()

DEFAULT_CONFIG = {
    "twitch_client_id": "",
    "twitch_access_token": "",  # 保存されたアクセストークン（自動ログイン用）
    "deepl_api_key": "",
    "channel_name": "",
    "channel_mode": "manual",  # auto: 認証アカウントと同じ, manual: 手動入力
    "translate_mode": "自動",
    "voicevox_url": "http://localhost:50021",
    "voicevox_speaker_id": 14,  # 冥鳴ひまり (Meimei Himari)
    "voicevox_engine_path": "",  # VOICEVOX Engineの実行ファイルパス
    "voicevox_auto_start": True,  # VOICEVOX Engineを自動起動するかどうか
    # Gladia STT設定
    "gladia_api_key": "",
    "gladia_usage_seconds": 0,  # 今月の使用秒数
    "gladia_reset_month": "",  # 最後にリセットした月 (例: "2025-12")
    "stt_provider": "gladia",  # 音声認識プロバイダー: "gladia" または "google"
    # イベント効果音
    "bits_sound_path": "",
    "bits_sound_volume": 80,
    "subscription_sound_path": "",  # 自分でサブスク
    "subscription_sound_volume": 80,
    "gift_sub_sound_path": "",  # ギフトサブ
    "gift_sub_sound_volume": 80,
    "follow_sound_path": "",  # フォロー
    "follow_sound_volume": 80,
    # 翻訳フィルタとカスタム辞書
    "translation_filters": [],
    "translation_dictionary": [],  # [{ "source": "原文", "target": "置換後" }]
    # コメント表示/出力設定
    "comment_log_bg": "#0E1728",
    "comment_log_fg": "#E8F0FF",
    "comment_log_font": "Consolas 11",
    "comment_bubble_style": "classic",  # classic / bubble / minimal
    "chat_html_output": False,
    "chat_html_path": "",
    "chat_html_newest_first": False,  # True: 上が新しい, False: 下が新しい
    "chat_html_window_geometry": "350x900+50+50",  # HTMLウィンドウのサイズと位置
    # コマンド機能
    "commands_enabled": True,
    # TTS設定
    "tts_volume": 80,
    "tts_speed": 1.0,
    "tts_include_name": False,
    # UI テーマ
    "ui_theme": "default",  # default / gradient / minimal / cyberpunk
    # ログ設定
    "log_level": "INFO",  # DEBUG / INFO / WARNING / ERROR
    # アップデート設定
    "auto_update_check": True,
    "include_prerelease": False,
    "last_update_check": "",
    "skipped_version": "",
}

VALID_TRANSLATE_MODES = {"自動", "英→日", "日→英"}
VALID_UI_THEMES = {"default", "gradient", "minimal", "cyberpunk"}
VALID_CHANNEL_MODES = {"auto", "manual"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}

def validate_config(config_data):
    """
    設定値を検証し、不足値をデフォルトで補完する
    Returns: (validated_config, changed: bool)
    """
    changed = False
    validated = DEFAULT_CONFIG.copy()
    validated.update(config_data or {})

    # translate_mode
    if validated.get("translate_mode") not in VALID_TRANSLATE_MODES:
        logger.warning(f"translate_mode is invalid: {validated.get('translate_mode')}, fallback to 自動")
        validated["translate_mode"] = "自動"
        changed = True

    # ui_theme
    if validated.get("ui_theme") not in VALID_UI_THEMES:
        logger.warning(f"ui_theme is invalid: {validated.get('ui_theme')}, fallback to default")
        validated["ui_theme"] = "default"
        changed = True

    # channel_mode
    if validated.get("channel_mode") not in VALID_CHANNEL_MODES:
        logger.warning(f"channel_mode is invalid: {validated.get('channel_mode')}, fallback to manual")
        validated["channel_mode"] = "manual"
        changed = True

    # log_level
    log_level = validated.get("log_level", "INFO").upper()
    if log_level not in VALID_LOG_LEVELS:
        logger.warning(f"log_level is invalid: {log_level}, fallback to INFO")
        validated["log_level"] = "INFO"
        changed = True
    else:
        validated["log_level"] = log_level

    # ブール値はbool化
    for key in ["voicevox_auto_start", "auto_update_check", "include_prerelease"]:
        if not isinstance(validated.get(key), bool):
            validated[key] = bool(validated.get(key))
            changed = True

    # 文字列系はNone回避
    for key in [
        "twitch_client_id",
        "twitch_access_token",
        "deepl_api_key",
        "channel_name",
        "channel_mode",
        "voicevox_url",
        "voicevox_engine_path",
        "gladia_api_key",
        "gladia_reset_month",
        "stt_provider",
        "bits_sound_path",
        "subscription_sound_path",
        "gift_sub_sound_path",
        "follow_sound_path",
        "comment_log_bg",
        "comment_log_fg",
        "comment_log_font",
        "comment_bubble_style",
        "chat_html_path",
        "ui_theme",
        "last_update_check",
        "skipped_version",
    ]:
        if validated.get(key) is None:
            validated[key] = DEFAULT_CONFIG.get(key, "")
            changed = True

    # リスト系
    if not isinstance(validated.get("translation_filters"), list):
        validated["translation_filters"] = []
        changed = True

    if not isinstance(validated.get("translation_dictionary"), list):
        validated["translation_dictionary"] = []
        changed = True

    # ブール系
    for key in ["chat_html_output", "chat_html_newest_first", "tts_include_name", "commands_enabled"]:
        if not isinstance(validated.get(key), bool):
            validated[key] = bool(validated.get(key))
            changed = True

    # translation_dictionary の正規化
    normalized_dict = []
    for entry in validated.get("translation_dictionary", []):
        if not isinstance(entry, dict):
            changed = True
            continue
        src = entry.get("source", "")
        tgt = entry.get("target", "")
        if not src and not tgt:
            continue
        normalized_dict.append({"source": str(src), "target": str(tgt)})
    if normalized_dict != validated.get("translation_dictionary", []):
        validated["translation_dictionary"] = normalized_dict
        changed = True

    return validated, changed

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            validated, changed = validate_config(raw)
            if changed:
                save_config(validated)
            return validated
    except Exception as e:
        logger.error(f"Failed to load config: {e}", exc_info=True)
        return DEFAULT_CONFIG.copy()

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save config: {e}", exc_info=True)

def check_gladia_usage(config_data):
    """
    Gladiaの使用時間をチェックし、月の制限に達しているか確認
    10時間（36000秒）を超えている場合はGoogle SRに自動切り替え
    新しい月になっている場合は使用時間をリセット

    Returns:
        bool: Gladiaが使用可能な場合True、制限超過でFalse
    """
    current_month = datetime.now().strftime("%Y-%m")
    reset_month = config_data.get("gladia_reset_month", "")
    usage_seconds = config_data.get("gladia_usage_seconds", 0)

    # 新しい月になったらリセット
    if reset_month != current_month:
        config_data["gladia_usage_seconds"] = 0
        config_data["gladia_reset_month"] = current_month
        config_data["stt_provider"] = "gladia"  # Gladiaに戻す
        save_config(config_data)
        logger.info(f"Gladia usage reset for new month: {current_month}")
        return True

    # 10時間（36000秒）の制限チェック
    MAX_SECONDS = 36000  # 10時間
    if usage_seconds >= MAX_SECONDS:
        if config_data.get("stt_provider") != "google":
            config_data["stt_provider"] = "google"
            save_config(config_data)
            logger.warning(f"Gladia usage limit reached ({usage_seconds}s / {MAX_SECONDS}s). Switched to Google SR.")
        return False

    return True

def update_gladia_usage(config_data, seconds):
    """
    Gladiaの使用時間を更新

    Args:
        config_data: 設定データ
        seconds: 追加する秒数
    """
    config_data["gladia_usage_seconds"] = config_data.get("gladia_usage_seconds", 0) + seconds
    save_config(config_data)

    remaining = 36000 - config_data["gladia_usage_seconds"]
    logger.info(f"Gladia usage: {config_data['gladia_usage_seconds']}s / 36000s (Remaining: {remaining}s / {remaining/3600:.1f}h)")


def validate_deepl_api_key(key: str) -> tuple[bool, str]:
    """
    DeepL APIキーの形式を検証

    Args:
        key: DeepL APIキー

    Returns:
        (is_valid, error_message)
    """
    if not key:
        return False, "DeepL APIキーが入力されていません"
    key = key.strip()
    # DeepL Free: ends with :fx, Pro: UUID-like format
    if key.endswith(":fx") and len(key) > 3:
        return True, ""
    if re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', key.lower()):
        return True, ""
    return False, "DeepL APIキーの形式が正しくありません（Free版は:fxで終わる形式、Pro版はUUID形式）"


def validate_twitch_client_id(client_id: str) -> tuple[bool, str]:
    """
    Twitch Client IDの形式を検証

    Args:
        client_id: Twitch Client ID

    Returns:
        (is_valid, error_message)
    """
    if not client_id:
        return False, "Twitch Client IDが入力されていません"
    client_id = client_id.strip()
    # Twitch Client ID: 30 alphanumeric characters
    if re.match(r'^[a-z0-9]{30}$', client_id.lower()):
        return True, ""
    return False, "Twitch Client IDの形式が正しくありません（30文字の英数字）"
