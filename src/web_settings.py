"""Webに公開する設定の許可リスト。秘密情報と内部設定を丸ごと返さない。"""

import math
import re
from urllib.parse import urlsplit

# key, label, type, group, constraints. UIもこの定義から作る。
FIELDS = []


def field(key, label, kind, group, **rules):
    FIELDS.append(dict(key=key, label=label, type=kind, group=group, **rules))


field("channel_name", "チャンネル名", "text", "接続", pattern=r"[a-zA-Z0-9_]{0,25}")
field("channel_mode", "接続先", "select", "接続", choices=["manual", "auto"], labels=["指定したチャンネル", "認証したアカウント"])
field("twitch_client_id", "Twitch Client ID（同梱版では空欄で利用可）", "text", "接続", pattern=r"[a-zA-Z0-9]{0,100}")
field("chat_translation_post_to_twitch", "翻訳をTwitchチャットにも投稿する", "checkbox", "接続")
field("translate_mode_2", "チャット投稿の追加言語", "select", "接続", choices=["", "自動", "英→日", "日→英"], labels=["オフ", "自動", "英→日", "日→英"])
field("tts_engine", "読み上げエンジン", "select", "音声", choices=["voicevox", "coeiroink", "aivisspeech", "sharevox", "edge-tts"])
field("tts_engine_url", "エンジンURL（空欄で標準設定）", "url", "音声")
field("voicevox_engine_path", "VOICEVOX実行ファイルのパス", "text", "音声")
field("voicevox_auto_start", "VOICEVOXを自動起動する", "checkbox", "音声")
field("voicevox_speaker_id", "VOICEVOX系ボイスID", "number", "音声", min=0, max=2147483647, step=1)
field("edge_tts_voice", "Edge TTSボイスID", "text", "音声", pattern=r"[a-zA-Z0-9-]{1,100}")
field("mic_device_index", "マイク", "microphone", "音声")
field("voice_chat_lang", "マイク翻訳の方向", "select", "音声", choices=["自動", "英→日", "日→英"])
field("voice_chat_lang_2", "マイク翻訳の追加言語", "select", "音声", choices=["", "自動", "英→日", "日→英"], labels=["オフ", "自動", "英→日", "日→英"])
field("voice_chat_format", "マイク翻訳の投稿形式", "text", "音声")
for key, label, low, high, step in [
    ("voice_chat_min_length", "投稿する最低文字数", 0, 200, 1),
    ("voice_chat_cooldown", "投稿間隔（秒）", 0, 300, 1),
    ("stt_num_threads", "音声認識のCPUスレッド数（再起動後）", 1, 16, 1),
    ("stt_vad_threshold", "音声検出のしきい値（再起動後）", .01, 1, .01),
]:
    field(key, label, "number", "音声", min=low, max=high, step=step)
field("ui_theme", "画面のテーマ", "select", "表示", choices=["default", "minimal", "gradient", "cyberpunk"], labels=["フォレスト", "ミニマル", "グラデーション", "サイバーパンク"])
field("web_workspace_layout", "ワークスペース", "select", "表示", choices=["studio", "focus"], labels=["スタジオ", "フォーカス"])
# 従来画面の全スタイルを引き継ぐ。欠けた選択肢はブラウザで空欄になり、他項目の保存も妨げる。
field("comment_bubble_style", "コメント表示", "select", "表示", choices=["classic", "modern", "box", "bubble", "neon", "cute", "minimal"])
field("comment_log_bg", "コメント背景色", "color", "表示")
field("comment_log_fg", "コメント文字色", "color", "表示")
field("comment_log_font", "コメントのフォント", "text", "表示")
field("chat_html_newest_first", "OBSコメントを新しい順に並べる", "checkbox", "表示")
field("chat_html_max_entries", "OBSコメントの最大表示件数", "number", "表示", min=1, max=5000, step=1)
for event, label in [("bits", "Bits"), ("subscription", "サブスク"), ("gift_sub", "ギフトサブ"), ("follow", "フォロー")]:
    field(f"{event}_sound_path", f"{label}の効果音ファイル", "text", "効果音")
    field(f"{event}_sound_volume", f"{label}の音量", "number", "効果音", min=0, max=100, step=1)
for key, label in [("enabled", "字幕を表示する"), ("show_original", "原文を表示する"), ("show_translated", "翻訳を表示する"), ("show_speaker", "話者を表示する"), ("show_timestamp", "時刻を表示する")]:
    field(f"subtitle_{key}", label, "checkbox", "字幕")
field("subtitle_font_family", "字幕フォント", "text", "字幕")
for key, label, low, high, step in [("font_size", "文字サイズ", 8, 120, 1), ("stroke_width", "縁取りの幅", 0, 10, 1), ("display_seconds", "表示時間（秒）", .5, 60, .5), ("max_lines", "最大行数", 1, 10, 1)]:
    field(f"subtitle_{key}", label, "number", "字幕", min=low, max=high, step=step)
field("subtitle_text_color", "字幕の文字色", "color", "字幕")
field("subtitle_stroke_color", "字幕の縁取り色", "color", "字幕")
field("obs_enabled", "OBS WebSocketに接続する", "checkbox", "OBS連携")
field("obs_host", "OBSホスト", "text", "OBS連携", pattern=r"[a-zA-Z0-9.:-]{1,253}")
field("obs_port", "OBSポート", "number", "OBS連携", min=1, max=65535, step=1)
field("obs_password", "OBSパスワード（空欄のままなら変更なし）", "password", "OBS連携")
for key, label in [("obs_auto_control_enabled", "配信状態と連動する"), ("obs_auto_start_bot", "配信開始時にBOTを開始する"), ("obs_auto_stop_bot", "配信終了時にBOTを停止する")]:
    field(key, label, "checkbox", "OBS連携")
for key, label in [("commands_enabled", "チャットコマンドを有効にする"), ("bot_filter_enabled", "既知のBOTを読み上げ・翻訳から除外する"), ("welcome_enabled", "初見の視聴者に挨拶する"), ("archive_enabled", "コメント履歴を保存する"), ("auto_update_check", "起動時に更新を確認する"), ("include_prerelease", "開発版の更新も含める"), ("telemetry_crash_reporting", "匿名のクラッシュレポートを送信する（任意）")]:
    field(key, label, "checkbox", "管理")
field("welcome_message", "初見への挨拶", "text", "管理")
field("archive_retention_days", "履歴の保持日数（0で無期限）", "number", "管理", min=0, max=3650, step=1)
field("log_level", "ログの詳細度", "select", "管理", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
BY_KEY = {item["key"]: item for item in FIELDS}


def validate_settings(value):
    from src.web_control import ControlError
    if not isinstance(value, dict) or not value or len(value) > len(FIELDS):
        raise ControlError("設定の形式が正しくありません。")
    result = {}
    for key, val in value.items():
        rule = BY_KEY.get(key)
        if rule is None:
            raise ControlError("変更できない設定が含まれています。")
        kind = rule["type"]
        if kind == "checkbox":
            valid = type(val) is bool
        elif kind == "number":
            valid = (type(val) in (int, float) and rule["min"] <= val <= rule["max"]
                     and math.isfinite(val) and (rule["step"] != 1 or val == int(val)))
        elif kind == "microphone":
            valid = val is None or type(val) is int and 0 <= val <= 65535
        else:
            valid = isinstance(val, str) and len(val) <= 1024 and not any(ord(c) < 32 for c in val)
            if valid:
                if kind != "password":
                    val = val.strip()
                if kind == "select":
                    valid = val in rule["choices"]
                elif kind == "color":
                    valid = bool(re.fullmatch(r"#[0-9a-fA-F]{6}", val))
                elif kind == "url" and val:
                    try:
                        url = urlsplit(val)
                        valid = (url.scheme in ("http", "https") and bool(url.hostname)
                                 and not url.username and not url.password and not url.query
                                 and not url.fragment and (url.port is None or url.port > 0))
                    except ValueError:
                        valid = False
                if "pattern" in rule:
                    valid = valid and bool(re.fullmatch(rule["pattern"], val))
        if not valid:
            raise ControlError(f"「{rule['label']}」の入力を確認してください。")
        if key == "obs_password" and val == "":
            continue  # 取得しない秘密情報を空欄フォームで上書きしない
        result[key] = val
    return result


def settings_snapshot(app):
    from src.config import DEFAULT_CONFIG
    values = {f["key"]: app.config.get(f["key"], DEFAULT_CONFIG.get(f["key"], ""))
              for f in FIELDS if f["type"] != "password"}
    values["mic_device_index"] = app.config.get("mic_device_index")
    engine = values["tts_engine"]
    values["tts_engine_url"] = app.config.get("tts_engine_urls", {}).get(engine, "")
    return {"fields": FIELDS, "values": values,
            "obs_password_set": bool(app.config.get("obs_password"))}


# 既存変数を同期し、BOTとネイティブ復旧画面も同じ設定を使う。
VARIABLES = {
    "channel_name": "channel", "channel_mode": "channel_mode", "twitch_client_id": "client_id",
    "translate_mode_2": "translate_mode_2_var", "voice_chat_lang": "voice_chat_lang_var",
    "voicevox_engine_path": "voicevox_path", "voicevox_auto_start": "voicevox_auto_start",
    "voicevox_speaker_id": "voicevox_speaker_id", "tts_engine": "tts_engine_var", "edge_tts_voice": "edge_tts_voice_var",
    "comment_log_bg": "comment_bg", "comment_log_fg": "comment_fg", "comment_log_font": "comment_font",
    "comment_bubble_style": "comment_bubble_style", "chat_html_newest_first": "chat_html_newest_first",
    "chat_html_max_entries": "chat_html_max_entries_var", "auto_update_check": "auto_update_check",
    "include_prerelease": "include_prerelease", "telemetry_crash_reporting": "telemetry_crash_reporting",
    "chat_translation_post_to_twitch": "chat_translation_post_to_twitch",
    "bits_sound_path": "bits_sound_path", "subscription_sound_path": "sub_sound_path",
    "gift_sub_sound_path": "gift_sub_sound_path", "follow_sound_path": "follow_sound_path",
    "bits_sound_volume": "bits_volume_var", "subscription_sound_volume": "sub_volume_var",
    "gift_sub_sound_volume": "gift_sub_volume_var", "follow_sound_volume": "follow_volume_var",
}
