import json
import os
import re
import sys
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
    "channel_name": "",
    "channel_mode": "manual",  # auto: 認証アカウントと同じ, manual: 手動入力
    "translate_mode": "自動",
    "translate_mode_2": "",              # 2言語目翻訳（空=無効、有効値: 自動/英→日/日→英）
    "voice_chat_lang": "日→英",          # 音声チャット専用の翻訳先言語1
    "voice_chat_lang_2": "",             # 音声チャット翻訳言語2（空=無効）
    "voice_chat_format": "[{lang}] {translation}",  # 音声チャット投稿フォーマット
    "voice_chat_min_length": 5,          # 音声チャット最低文字数（0=制限なし）
    "voice_chat_cooldown": 3,            # 音声チャット連続投稿クールダウン（秒）
    "voicevox_url": "http://localhost:50021",
    "voicevox_speaker_id": 14,  # 冥鳴ひまり (Meimei Himari)
    "voicevox_engine_path": "",  # VOICEVOX Engineの実行ファイルパス
    "voicevox_auto_start": True,  # VOICEVOX Engineを自動起動するかどうか
    # TTSエンジン選択: voicevox / coeiroink / aivisspeech / sharevox / edge-tts
    "tts_engine": "voicevox",
    # エンジン別URLの上書き（空なら各エンジンのデフォルトポート）
    "tts_engine_urls": {},
    # Edge TTS のデフォルトボイス（engine_name="edge-tts" のときに使われる）
    "edge_tts_voice": "ja-JP-NanamiNeural",
    # ローカルSTT設定
    "stt_num_threads": 2,          # sherpa-onnx CPU threads
    "stt_vad_threshold": 0.3,     # Silero VAD threshold (0.01-1.0)
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
    "translation_dictionary": [],  # migration用: translation_dict.jsonに移行済みなら空
    # コメント表示/出力設定
    "comment_log_bg": "#0E1728",
    "comment_log_fg": "#E8F0FF",
    "comment_log_font": "Consolas 11",
    "comment_bubble_style": "classic",  # classic / bubble / minimal
    "chat_html_output": False,
    "chat_html_path": "",
    "chat_html_newest_first": False,  # True: 上が新しい, False: 下が新しい
    "chat_html_max_entries": 200,     # HTML に表示するコメントの最大件数 (1-5000)
    "chat_html_window_geometry": "350x900+50+50",  # HTMLウィンドウのサイズと位置
    # コマンド機能
    "commands_enabled": True,
    # !clip コマンド設定
    "clip_enabled": True,
    "clip_permission_level": 3,   # PermissionLevel: 0=全員 1=サブスク 2=VIP 3=モデレーター 4=配信者
    "clip_cooldown": 60,           # グローバルクールダウン（秒）
    "clip_reply": True,            # クリップURLをチャットに返信するか
    # ボイス割り当て設定
    "voice_assign_mode": "mod_only",  # mod_only / self_service / disabled
    "voice_self_assign_min_visits": 5,  # セルフ割り当てに必要な最低視聴回数
    "voice_allowed_speakers": [],  # 空=全て許可、指定=制限
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
    # ロールバック設定
    "previous_version": "",          # ロールバック可能な前バージョン (例: "v1.5.0-beta.3")
    "just_updated": False,           # アップデート直後フラグ
    "previous_installer_url": "",    # 前バージョンのインストーラーURL
    # チャンネル履歴（接続成功順・最大20件）
    "channel_history": [],           # [{"login": str, "display_name": str, "user_id": str, "last_connected_at": str}]
    # 字幕オーバーレイ設定
    "subtitle_enabled": False,
    "subtitle_show_original": True,
    "subtitle_show_translated": True,
    "subtitle_show_speaker": False,
    "subtitle_show_timestamp": False,
    "subtitle_font_family": "Noto Sans JP",
    "subtitle_font_size": 32,
    "subtitle_text_color": "#FFFFFF",
    "subtitle_stroke_color": "#000000",
    "subtitle_stroke_width": 3,
    "subtitle_display_seconds": 5.0,
    "subtitle_max_lines": 3,
    # OBS連携
    "obs_enabled": False,
    "obs_host": "127.0.0.1",
    "obs_port": 4455,
    "obs_password": "",
    "obs_poll_interval_sec": 1.0,
    "obs_auto_control_enabled": True,
    "obs_auto_start_bot": True,
    "obs_auto_stop_bot": True,
    "obs_scene_rules": [],  # [{"scene": "休憩", "tts_mute": True, "show_sources": [], "hide_sources": []}]
    # BOT フィルタリング
    "bot_filter_enabled": True,     # 既知 BOT を TTS・翻訳から自動除外
    "bot_filter_custom": [],        # ユーザー定義の追加 BOT リスト
    # セッションアーカイブ
    "archive_enabled": True,        # コメントログの自動保存
    "archive_retention_days": 90,   # 保持期間（日数、0=無制限）
    # ゲーム機能
    "game_enabled": True,           # ゲームコマンドの有効/無効
    "game_fortune_cooldown": 30,    # おみくじクールダウン（秒）
    "game_dice_cooldown": 5,        # さいころクールダウン（秒）
    "game_coin_cooldown": 5,        # コイントスクールダウン（秒）
    "game_slot_cooldown": 10,       # スロットクールダウン（秒）
    "game_roulette_cooldown": 10,   # ルーレットクールダウン（秒）
    "game_janken_cooldown": 5,      # じゃんけんクールダウン（秒）
    "game_guess_cooldown": 3,       # 数字当てクールダウン（秒）
}

VALID_TRANSLATE_MODES = {"自動", "英→日", "日→英"}
VALID_UI_THEMES = {"default", "gradient", "minimal", "cyberpunk"}


def get_valid_ui_themes() -> set[str]:
    """builtin + カスタムテーマのキー集合を返す（Issue #38 Phase A）。"""
    themes = set(VALID_UI_THEMES)
    try:
        # 循環 import 回避のため関数内 import
        from src.gui import THEMES as _GUI_THEMES  # noqa: PLC0415

        themes.update(_GUI_THEMES.keys())
    except Exception:
        # GUI 未ロード時は JSON から直接読む
        try:
            from src.theme_loader import get_themes_dir  # noqa: PLC0415
            import os as _os  # noqa: PLC0415

            directory = get_themes_dir()
            if _os.path.isdir(directory):
                for name in _os.listdir(directory):
                    if name.lower().endswith(".json"):
                        themes.add(_os.path.splitext(name)[0])
        except Exception:
            pass
    return themes
VALID_CHANNEL_MODES = {"auto", "manual"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
VALID_VOICE_ASSIGN_MODES = {"mod_only", "self_service", "disabled"}
VALID_TTS_ENGINES = {"voicevox", "coeiroink", "aivisspeech", "sharevox", "edge-tts"}
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

    # translate_mode_2 の検証
    t2 = validated.get("translate_mode_2", "")
    if t2 and t2 not in VALID_TRANSLATE_MODES:
        validated["translate_mode_2"] = ""
        changed = True

    # voice_chat_lang の検証
    if validated.get("voice_chat_lang", "") not in VALID_TRANSLATE_MODES:
        validated["voice_chat_lang"] = "日→英"
        changed = True

    # voice_chat_lang_2 の検証
    vl2 = validated.get("voice_chat_lang_2", "")
    if vl2 and vl2 not in VALID_TRANSLATE_MODES:
        validated["voice_chat_lang_2"] = ""
        changed = True

    # voice_chat_format の検証
    if not isinstance(validated.get("voice_chat_format"), str):
        validated["voice_chat_format"] = "[{lang}] {translation}"
        changed = True

    # voice_chat_min_length の検証 (0-1000)
    try:
        vml = int(validated.get("voice_chat_min_length", 5))
        validated["voice_chat_min_length"] = max(0, min(1000, vml))
    except (TypeError, ValueError):
        validated["voice_chat_min_length"] = 5
        changed = True

    # voice_chat_cooldown の検証 (0-300)
    try:
        vcd = int(validated.get("voice_chat_cooldown", 3))
        validated["voice_chat_cooldown"] = max(0, min(300, vcd))
    except (TypeError, ValueError):
        validated["voice_chat_cooldown"] = 3
        changed = True

    # ui_theme (builtin + カスタムテーマを許容)
    if validated.get("ui_theme") not in get_valid_ui_themes():
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
    for key in ["voicevox_auto_start", "auto_update_check", "include_prerelease", "archive_enabled"]:
        if not isinstance(validated.get(key), bool):
            validated[key] = bool(validated.get(key))
            changed = True

    # 文字列系はNone回避
    for key in [
        "twitch_client_id",
        "twitch_access_token",
        "channel_name",
        "channel_mode",
        "voicevox_url",
        "voicevox_engine_path",
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
        "previous_version",
        "previous_installer_url",
    ]:
        if validated.get(key) is None:
            validated[key] = DEFAULT_CONFIG.get(key, "")
            changed = True

    # 旧翻訳設定はローカル翻訳固定化に伴い除去
    for legacy_key in ("deepl_api_key", "translation_engine"):
        if legacy_key in validated:
            validated.pop(legacy_key, None)
            changed = True

    if config_data and any(key in config_data for key in ("deepl_api_key", "translation_engine")):
        changed = True

    # tts_engine
    if validated.get("tts_engine") not in VALID_TTS_ENGINES:
        logger.warning(
            "tts_engine is invalid: %s, fallback to voicevox",
            validated.get("tts_engine"),
        )
        validated["tts_engine"] = "voicevox"
        changed = True

    # tts_engine_urls は dict[str, str]
    engine_urls = validated.get("tts_engine_urls")
    if not isinstance(engine_urls, dict):
        validated["tts_engine_urls"] = {}
        changed = True
    else:
        normalized_urls: dict[str, str] = {}
        for key, value in engine_urls.items():
            if key in VALID_TTS_ENGINES and isinstance(value, str) and value.strip():
                normalized_urls[key] = value.strip()
            else:
                changed = True
        if normalized_urls != engine_urls:
            validated["tts_engine_urls"] = normalized_urls
            changed = True

    # edge_tts_voice は ja-JP-*Neural のような string
    etv = validated.get("edge_tts_voice")
    if not isinstance(etv, str) or not etv.strip():
        validated["edge_tts_voice"] = "ja-JP-NanamiNeural"
        changed = True

    # voice_assign_mode
    if validated.get("voice_assign_mode") not in VALID_VOICE_ASSIGN_MODES:
        logger.warning(
            "voice_assign_mode is invalid: %s, fallback to mod_only",
            validated.get("voice_assign_mode"),
        )
        validated["voice_assign_mode"] = "mod_only"
        changed = True

    # voice_self_assign_min_visits (int >= 0)
    try:
        validated["voice_self_assign_min_visits"] = max(
            0, int(validated.get("voice_self_assign_min_visits", 5))
        )
    except (TypeError, ValueError):
        validated["voice_self_assign_min_visits"] = 5
        changed = True

    # stt_num_threads (int, 1-8)
    try:
        stt_threads = int(validated.get("stt_num_threads", 2))
        validated["stt_num_threads"] = max(1, min(8, stt_threads))
    except (TypeError, ValueError):
        validated["stt_num_threads"] = 2
        changed = True

    # stt_vad_threshold (float, 0.01-1.0)
    try:
        vad_threshold = float(validated.get("stt_vad_threshold", 0.3))
        validated["stt_vad_threshold"] = max(0.01, min(1.0, vad_threshold))
    except (TypeError, ValueError):
        validated["stt_vad_threshold"] = 0.3
        changed = True

    # chat_html_max_entries (int, 1-5000)
    try:
        max_entries = int(validated.get("chat_html_max_entries", 200))
        validated["chat_html_max_entries"] = max(1, min(5000, max_entries))
    except (TypeError, ValueError):
        validated["chat_html_max_entries"] = 200
        changed = True

    # archive_retention_days (int, 0=無制限, 1-3650)
    try:
        retention = int(validated.get("archive_retention_days", 90))
        validated["archive_retention_days"] = max(0, min(3650, retention))
    except (TypeError, ValueError):
        validated["archive_retention_days"] = 90
        changed = True

    # リスト系
    if not isinstance(validated.get("translation_filters"), list):
        validated["translation_filters"] = []
        changed = True

    if not isinstance(validated.get("translation_dictionary"), list):
        validated["translation_dictionary"] = []
        changed = True

    if not isinstance(validated.get("voice_allowed_speakers"), list):
        validated["voice_allowed_speakers"] = []
        changed = True

    # channel_history の正規化
    if not isinstance(validated.get("channel_history"), list):
        validated["channel_history"] = []
        changed = True
    else:
        cleaned = []
        for h in validated["channel_history"]:
            if isinstance(h, dict) and h.get("login"):
                cleaned.append({
                    "login": str(h["login"]).lower(),
                    "display_name": str(h.get("display_name") or h["login"]),
                    "user_id": str(h.get("user_id") or ""),
                    "last_connected_at": str(h.get("last_connected_at") or ""),
                })
        if cleaned != validated["channel_history"]:
            validated["channel_history"] = cleaned
            changed = True

    # channel_name からの移行: channel_history が空かつ channel_name が存在する場合
    if not validated.get("channel_history") and validated.get("channel_name"):
        login = validated["channel_name"].lower()
        validated["channel_history"] = [{"login": login, "display_name": login, "user_id": "", "last_connected_at": ""}]
        changed = True

    # ブール系
    for key in ["chat_html_output", "chat_html_newest_first", "tts_include_name", "commands_enabled", "just_updated"]:
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

    # subtitle_font_size (int, 8-200)
    try:
        validated["subtitle_font_size"] = max(8, min(200, int(validated.get("subtitle_font_size", 32))))
    except (TypeError, ValueError):
        validated["subtitle_font_size"] = 32
        changed = True

    # subtitle_stroke_width (int, 0-20)
    try:
        validated["subtitle_stroke_width"] = max(0, min(20, int(validated.get("subtitle_stroke_width", 3))))
    except (TypeError, ValueError):
        validated["subtitle_stroke_width"] = 3
        changed = True

    # subtitle_display_seconds (float, 1.0-60.0)
    try:
        validated["subtitle_display_seconds"] = max(1.0, min(60.0, float(validated.get("subtitle_display_seconds", 5.0))))
    except (TypeError, ValueError):
        validated["subtitle_display_seconds"] = 5.0
        changed = True

    # subtitle_max_lines (int, 1-10)
    try:
        validated["subtitle_max_lines"] = max(1, min(10, int(validated.get("subtitle_max_lines", 3))))
    except (TypeError, ValueError):
        validated["subtitle_max_lines"] = 3
        changed = True

    # subtitle bool フラグ
    for key in ["subtitle_enabled", "subtitle_show_original", "subtitle_show_translated",
                "subtitle_show_speaker", "subtitle_show_timestamp"]:
        if not isinstance(validated.get(key), bool):
            validated[key] = bool(validated.get(key))
            changed = True

    # OBS bool フラグ
    for key in ["obs_enabled", "obs_auto_control_enabled", "obs_auto_start_bot", "obs_auto_stop_bot"]:
        if not isinstance(validated.get(key), bool):
            validated[key] = bool(validated.get(key))
            changed = True

    # subtitle 文字列系
    for key in ["subtitle_font_family", "subtitle_text_color", "subtitle_stroke_color"]:
        if not isinstance(validated.get(key), str):
            validated[key] = DEFAULT_CONFIG.get(key, "")
            changed = True

    # OBS 文字列系
    for key in ["obs_host", "obs_password"]:
        if validated.get(key) is None:
            validated[key] = DEFAULT_CONFIG.get(key, "")
            changed = True
        elif not isinstance(validated.get(key), str):
            validated[key] = str(validated.get(key))
            changed = True

    # OBS ポート (int, 1-65535)
    try:
        validated["obs_port"] = max(1, min(65535, int(validated.get("obs_port", 4455))))
    except (TypeError, ValueError):
        validated["obs_port"] = 4455
        changed = True

    # OBS ポーリング間隔 (float, 0.2-10.0)
    try:
        validated["obs_poll_interval_sec"] = max(0.2, min(10.0, float(validated.get("obs_poll_interval_sec", 1.0))))
    except (TypeError, ValueError):
        validated["obs_poll_interval_sec"] = 1.0
        changed = True

    # OBS シーンルール正規化
    rules = validated.get("obs_scene_rules", [])
    if not isinstance(rules, list):
        validated["obs_scene_rules"] = []
        changed = True
    else:
        normalized_rules = []
        for rule in rules:
            if not isinstance(rule, dict):
                changed = True
                continue
            scene_name = str(rule.get("scene", "")).strip()
            if not scene_name:
                changed = True
                continue
            tts_mute = rule.get("tts_mute", None)
            if tts_mute is not None:
                tts_mute = bool(tts_mute)
            show_sources = rule.get("show_sources", [])
            hide_sources = rule.get("hide_sources", [])
            if not isinstance(show_sources, list):
                show_sources = []
                changed = True
            if not isinstance(hide_sources, list):
                hide_sources = []
                changed = True
            normalized_rules.append({
                "scene": scene_name,
                "tts_mute": tts_mute,
                "show_sources": [str(x).strip() for x in show_sources if str(x).strip()],
                "hide_sources": [str(x).strip() for x in hide_sources if str(x).strip()],
            })
        if normalized_rules != rules:
            validated["obs_scene_rules"] = normalized_rules
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

def _rotate_backups() -> None:
    """config.json の自動バックアップを最大3世代ローテーションする。

    世代: config.json.bak → config.json.bak.2 → config.json.bak.3
    """
    import shutil
    bak1 = CONFIG_FILE + ".bak"
    bak2 = CONFIG_FILE + ".bak.2"
    bak3 = CONFIG_FILE + ".bak.3"
    try:
        if os.path.exists(bak2):
            shutil.copy2(bak2, bak3)
        if os.path.exists(bak1):
            shutil.copy2(bak1, bak2)
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, bak1)
    except Exception as e:
        logger.warning(f"Failed to rotate config backups: {e}")


def save_config(config_data):
    _rotate_backups()
    try:
        validated, _ = validate_config(config_data)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(validated, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save config: {e}", exc_info=True)


def backup_config(dst_path: str) -> bool:
    """現在の設定ファイルを指定パスにバックアップする。

    Args:
        dst_path: 保存先ファイルパス。

    Returns:
        成功した場合 True。
    """
    import shutil
    try:
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, dst_path)
        else:
            with open(dst_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG.copy(), f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to backup config: {e}", exc_info=True)
        return False


def restore_config(src_path: str) -> bool:
    """バックアップファイルから設定を復元する。

    src_path の JSON を読み込んで validate_config() を通し、
    CONFIG_FILE に保存する。

    Args:
        src_path: 復元元ファイルパス。

    Returns:
        成功した場合 True。
    """
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        validated, _ = validate_config(raw)
        save_config(validated)
        return True
    except Exception as e:
        logger.error(f"Failed to restore config: {e}", exc_info=True)
        return False


def reset_config() -> dict:
    """設定をデフォルト値にリセットして保存する。

    Returns:
        リセット後の設定辞書。
    """
    defaults = DEFAULT_CONFIG.copy()
    save_config(defaults)
    return defaults


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
