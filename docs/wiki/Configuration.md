# 設定

設定は `config.json` に自動保存されます。

## Twitch接続

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `twitch_client_id` | Twitch Client ID | `""` |
| `twitch_access_token` | アクセストークン（自動取得） | `""` |
| `channel_name` | 接続するチャンネル名 | `""` |
| `channel_mode` | `auto`（認証アカウント）または `manual` | `"manual"` |

## 翻訳設定

翻訳はローカルエンジン固定です。DeepL API Key の設定項目はありません。

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

### クリップコマンド設定

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `clip_enabled` | `!clip` コマンドの有効/無効 | `true` |
| `clip_permission_level` | 必要権限（0=全員〜4=配信者） | `3`（モデレーター） |
| `clip_cooldown` | グローバルクールダウン（秒） | `60` |
| `clip_reply` | クリップURLをチャットに返信するか | `true` |

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
