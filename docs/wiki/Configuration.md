# 設定

設定は `config.json` に自動保存されます。

## Twitch接続

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `twitch_client_id` | Twitch Client ID | `""` |
| `twitch_access_token` | アクセストークン（自動取得） | `""` |
| `channel_name` | 接続するチャンネル名 | `""` |
| `channel_mode` | `auto`（認証アカウント）または `manual` | `"manual"` |

## API設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `deepl_api_key` | DeepL API Key | `""` |
| `gladia_api_key` | Gladia API Key | `""` |
| `gladia_usage_seconds` | 今月のGladia使用秒数 | `0` |
| `gladia_reset_month` | 使用量リセット月 | `""` |
| `stt_provider` | 音声認識プロバイダ（`gladia`/`google`） | `"gladia"` |

## 翻訳設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `translate_mode` | 翻訳モード（`自動`/`英→日`/`日→英`） | `"自動"` |
| `chat_translation_enabled` | チャット翻訳の有効/無効 | `false` |
| `translation_filters` | 翻訳スキップワード | `[]` |
| `translation_dictionary` | カスタム辞書 | `[]` |
| `commands_enabled` | チャットコマンド機能の有効/無効 | `true` |
| `translation_batch_size` | バッチ翻訳の最大件数 | `5` |
| `translation_batch_wait_ms` | バッチ翻訳の待機時間（ms） | `100` |

### カスタム辞書の形式

```json
"translation_dictionary": [
  { "source": "YAGOO", "target": "谷郷" },
  { "source": "kusa", "target": "草" }
]
```

## コマンド設定

チャットコマンド機能は `config.json` の `commands_enabled` で有効/無効を切り替えます。

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `commands_enabled` | コマンド機能の有効/無効 | `true` |

### カスタムコマンド（custom_commands.json）

カスタムコマンドは `custom_commands.json` に保存されます（`config.json` とは別ファイル）。

```json
{
  "version": 1,
  "commands": [
    {
      "name": "discord",
      "response": "Discordはこちら: https://discord.gg/xxx",
      "permission": 0,
      "cooldown_global": 5.0,
      "cooldown_user": 15.0,
      "enabled": true
    }
  ]
}
```

| フィールド | 説明 | デフォルト |
|-----------|------|-----------|
| `name` | コマンド名（`!`なし） | — |
| `response` | 応答テンプレート | — |
| `permission` | 必要権限（0=全員〜4=配信者） | `0` |
| `cooldown_global` | グローバルクールダウン（秒） | `5.0` |
| `cooldown_user` | ユーザー別クールダウン（秒） | `15.0` |
| `enabled` | 有効/無効 | `true` |

## VOICEVOX設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `voicevox_url` | VOICEVOX APIのURL | `"http://localhost:50021"` |
| `voicevox_speaker_id` | ボイスID | `14`（冥鳴ひまり） |
| `voicevox_engine_path` | VOICEVOX Engineのパス | `""` |
| `voicevox_auto_start` | 自動起動の有効/無効 | `true` |

### ボイスID一覧（例）

| ID | キャラクター |
|----|------------|
| 0 | 四国めたん（ノーマル） |
| 2 | 四国めたん（あまあま） |
| 3 | ずんだもん（ノーマル） |
| 14 | 冥鳴ひまり |

※実際のIDはVOICEVOXのバージョンにより異なります

## イベント効果音

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `bits_sound_path` | Bits効果音ファイルパス | `""` |
| `bits_sound_volume` | Bits効果音音量（0-100） | `80` |
| `subscription_sound_path` | サブスク効果音パス | `""` |
| `subscription_sound_volume` | サブスク効果音音量 | `80` |
| `gift_sub_sound_path` | ギフトサブ効果音パス | `""` |
| `gift_sub_sound_volume` | ギフトサブ効果音音量 | `80` |
| `follow_sound_path` | フォロー効果音パス | `""` |
| `follow_sound_volume` | フォロー効果音音量 | `80` |

## UI設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `ui_theme` | UIテーマ | `"default"` |
| `log_level` | ログレベル | `"INFO"` |
| `comment_log_bg` | コメントログ背景色 | `"#0E1728"` |
| `comment_log_fg` | コメントログ文字色 | `"#E8F0FF"` |
| `comment_log_font` | コメントログフォント | `"Consolas 11"` |
| `comment_bubble_style` | バブルスタイル | `"classic"` |

### UIテーマ

| 値 | 説明 |
|----|------|
| `default` | デフォルト（クラシック） |
| `gradient` | グラデーション（モダン） |
| `minimal` | ミニマル（ライトモード） |
| `cyberpunk` | サイバーパンク（ゲーミング） |

### バブルスタイル

`classic`, `modern`, `box`, `bubble`, `neon`, `cute`, `minimal`

## チャットHTML出力設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `chat_html_output` | チャットHTML出力の有効/無効 | `false` |
| `chat_html_path` | HTML ファイルの出力先パス | `""` |
| `chat_html_newest_first` | 最新コメントを上に表示するか | `false` |
| `chat_html_max_entries` | HTML に表示する最大件数（1〜5000） | `200` |

## 字幕オーバーレイ設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `subtitle_enabled` | 字幕オーバーレイの有効/無効 | `false` |
| `subtitle_show_original` | 原文を表示するか | `true` |
| `subtitle_show_translated` | 翻訳文を表示するか | `true` |
| `subtitle_show_speaker` | 話者名を表示するか | `false` |
| `subtitle_show_timestamp` | タイムスタンプを表示するか | `false` |
| `subtitle_font_family` | フォント名 | `"Noto Sans JP"` |
| `subtitle_font_size` | フォントサイズ（8〜200） | `32` |
| `subtitle_text_color` | 文字色（16進数） | `"#FFFFFF"` |
| `subtitle_stroke_color` | 縁取り色（16進数） | `"#000000"` |
| `subtitle_stroke_width` | 縁取り幅（0〜20） | `3` |
| `subtitle_display_seconds` | 表示持続時間（秒、1.0〜60.0） | `5.0` |
| `subtitle_max_lines` | 最大行数（1〜10） | `3` |

## OBS WebSocket 設定

OBS WebSocket 連携の設定です。詳細は [OBS連携ガイド](OBS-Setup) を参照してください。

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `obs_enabled` | OBS WebSocket 連携の有効/無効 | `false` |
| `obs_host` | OBS が動作しているホスト名または IP | `"127.0.0.1"` |
| `obs_port` | OBS WebSocket のポート番号 | `4455` |
| `obs_password` | OBS WebSocket のパスワード | `""` |
| `obs_poll_interval_sec` | ポーリング間隔（秒、0.2〜10.0） | `1.0` |
| `obs_auto_control_enabled` | 自動制御機能全体の有効/無効 | `true` |
| `obs_auto_start_bot` | 配信開始時に BOT を自動起動 | `true` |
| `obs_auto_stop_bot` | 配信終了時に BOT を自動停止 | `true` |
| `obs_scene_rules` | シーンルールの配列（下記参照） | `[]` |

### シーンルールの形式

```json
"obs_scene_rules": [
  {
    "scene": "休憩",
    "tts_mute": true,
    "show_sources": ["BreakCard"],
    "hide_sources": ["AlertOverlay"]
  }
]
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `scene` | string | OBS のシーン名（大文字小文字を区別しない） |
| `tts_mute` | boolean | `true` で TTS をミュート、`false` で解除 |
| `show_sources` | string[] | 表示するソース名の配列 |
| `hide_sources` | string[] | 非表示にするソース名の配列 |

## アップデート設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `auto_update_check` | 起動時にアップデートを確認 | `true` |
| `include_prerelease` | プレリリースも含めて確認 | `false` |

## パフォーマンス設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `chat_log_history_limit` | ログ履歴の保持上限数 | `1000` |
| `participant_limit` | 参加者リストの上限数 | `1000` |
| `auto_restart_enabled` | メモリ超過時の自動再起動 | `false` |
| `auto_restart_threshold_mb` | 自動再起動のメモリ閾値（MB） | `1000` |

### 自動再起動

`auto_restart_enabled` を `true` にすると、メモリ使用量が `auto_restart_threshold_mb` を超えた時にダイアログを表示し、ユーザーの確認後にアプリケーションを再起動します。

## 設定ファイルの場所

- Windows: `<プロジェクトフォルダ>/config.json`
- 起動時に自動読み込み
- 変更時に自動保存
