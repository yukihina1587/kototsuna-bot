# ことつな！ - Twitch翻訳BOT

[![Tests](https://github.com/yukihina1587/kototsuna-bot/actions/workflows/test.yml/badge.svg)](https://github.com/yukihina1587/kototsuna-bot/actions/workflows/test.yml)

Twitchのチャットメッセージをリアルタイムで翻訳するBOTです。DeepL APIを利用した高品質な翻訳と、VOICEVOXによる読み上げ機能を搭載しています。

## 主な機能

### チャット翻訳
- 日本語⇔英語の双方向自動翻訳（DeepL API）
- 翻訳モード選択（自動 / 英→日 / 日→英）
- 翻訳のオン/オフ切り替え
- 翻訳フィルター（特定ワードをスキップ）
- カスタム辞書（翻訳前の置換）

### 音声機能
- **チャット読み上げ（TTS）**: VOICEVOXによる高品質な音声読み上げ
  - 複数のボイスから選択可能
  - VOICEVOX未起動時はpyttsx3にフォールバック
- **音声翻訳（マイク入力）**: マイクに向かって喋った内容を翻訳
  - Gladia API（リアルタイム音声認識）
  - Google Speech Recognition（フォールバック）

### Twitchイベント検知
- **フォロー通知**: EventSub WebSocketで検知
- **サブスク通知**: 新規サブスク、継続サブスク
- **ギフトサブ通知**: ギフトサブ、ミステリーギフト
- **Bits（チア）通知**: 金額とメッセージ表示
- **イベント効果音**: 各イベントに個別の効果音を設定可能（ボリューム調整付き）

### その他の機能
- **オーバーレイサーバー**: OBS等で使用可能な翻訳オーバーレイ
- **参加者追跡**: キーワード検知で参加者を自動登録
- **チャットコマンド**: `!help`, `!translate`等のビルトインコマンド + カスタムコマンド
- **読み上げ辞書**: 漢字の読み間違いを修正
- **UIテーマ**: 4種類のテーマから選択可能
- **ログレベル切り替え**: DEBUG/INFO/WARNING/ERRORの動的切り替え
- **API安定性**: ネットワークエラー時の自動リトライ（指数バックオフ）
- **リソース監視**: メモリ/CPU/スレッドのリアルタイム監視
- **パフォーマンス最適化**: 翻訳バッチ処理、GUI差分更新、メモリ自動制限
- **自動アップデート**: GitHub Releasesからの自動更新チェック

## 必要なもの

- Python 3.10以上（3.12推奨）
- Twitchアカウント
- DeepL APIキー（Free版またはPro版）
- マイク（音声翻訳機能を使用する場合）
- VOICEVOX Engine（高品質な読み上げを使用する場合、オプション）
- Gladia APIキー（高品質な音声認識を使用する場合、オプション）

## セットアップ手順

### 1. ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 2. Twitchアプリケーションの登録

1. [Twitch Developers](https://dev.twitch.tv/console)にアクセス
2. 「アプリケーション」→「アプリケーションを登録」
3. 以下の情報を入力:
   - **名前**: 任意（例: `MyTranslateBot`）
   - **OAuthリダイレクトURL**: `http://localhost:8787/redirect.html`
   - **カテゴリ**: `チャットボット`
4. 作成後、**クライアントID**をメモ

### 3. DeepL APIキーの取得

1. [DeepL公式サイト](https://www.deepl.com/pro-api)でAPIキーを取得
2. Free版でも動作します

### 4. VOICEVOX Engineのインストール（オプション）

1. [VOICEVOX公式サイト](https://voicevox.hiroshiba.jp/)からダウンロード
2. インストール後、起動（デフォルト: `http://localhost:50021`）

**フォールバック**: VOICEVOX未起動時は自動的にpyttsx3にフォールバックします。

### 5. Gladia APIキーの取得（オプション）

1. [Gladia公式サイト](https://www.gladia.io/)でAPIキーを取得
2. 月10時間まで無料で使用可能
3. 制限超過時はGoogle Speech Recognitionに自動切り替え

### 6. 実行

```bash
python main.py
```

## 使い方

### 初回起動時

1. **Twitch Client ID**を設定パネルに入力
2. **DeepL API Key**を設定パネルに入力
3. **トークン認証**ボタンをクリック → ブラウザでTwitch認証
4. **チャンネル名**を入力（または認証アカウントと同じを選択）
5. **BOT起動**ボタンをクリック

### 画面構成

```
┌─────────────────────────────────────────────────────────────┐
│ ヘッダー: タイトル / 接続状態 / 統計 / 認証・起動ボタン      │
├──────┬──────────────────────────────────┬───────────────────┤
│      │                                  │                   │
│ 左   │    メインコンテンツ              │    右パネル       │
│ サイド│    - コメントログ                │    - 設定         │
│ バー  │    - システムログ                │    - 辞書         │
│      │    - 特別イベント                │    - 参加者       │
│      │    - 参加者リスト                │    - コマンド     │
│      │                                  │                   │
└──────┴──────────────────────────────────┴───────────────────┘
```

### 左サイドバー

- **TTS**: チャット読み上げのオン/オフ
- **チャット翻訳**: 翻訳機能のオン/オフ
- **効果音**: 各イベントの効果音再生・ボリューム調整

### 右パネル（設定）

| セクション | 設定項目 |
|-----------|---------|
| Twitch接続 | 認証アカウント、チャンネル選択 |
| API設定 | DeepL Key、Gladia Key |
| マイク選択 | 使用するマイクデバイス |
| VOICEVOX | パス、自動起動、ボイス選択 |
| UIテーマ | デフォルト/グラデーション/ミニマル/サイバーパンク |
| ログレベル | DEBUG/INFO/WARNING/ERROR |
| コメントログ外観 | 背景色、テキスト色、フォント |
| イベント効果音 | Bits/サブスク/ギフトサブ/フォローの効果音 |

### 右パネル（辞書）

| 辞書 | 説明 |
|-----|------|
| 読み上げ辞書 | 漢字の読み間違いを修正（例: 草→くさ） |
| 翻訳フィルター | 翻訳をスキップするワード |
| 翻訳カスタム辞書 | 翻訳前に置換するワード |

### 右パネル（コマンド）

| 機能 | 説明 |
|-----|------|
| コマンドON/OFF | チャットコマンド機能の有効/無効 |
| カスタムコマンド追加 | コマンド名・応答・権限・クールダウンを設定 |
| コマンドリスト | 登録済みコマンドの確認・削除 |

### チャットコマンド

| コマンド | 権限 | 説明 |
|---------|------|------|
| `!help` | 全員 | コマンド一覧を表示 |
| `!translate <テキスト>` | 全員 | テキストを翻訳 |
| `!lang` | 全員 | 現在の翻訳モードを表示 |
| `!tts on/off` | モデレーター | TTS読み上げの切替 |
| `!voice` | モデレーター | VOICEVOXボイス一覧 |

カスタムコマンドはGUIの「コマンド」パネルから追加できます。応答テンプレートでは `{user}`, `{channel}`, `{time}`, `{date}` の変数が使用可能です。

## オーバーレイ機能

OBSなどの配信ソフトでブラウザソースとして使用できます。

- **URL**: `http://localhost:8080/overlay.html`（ポートは自動検索）
- **API**:
  - `GET /api/current` - 現在の翻訳テキスト
  - `GET /api/history` - 翻訳履歴（最新50件）

## 設定ファイル

設定は `config.json` に自動保存されます。

<details>
<summary>主な設定キー</summary>

| キー | 説明 | デフォルト |
|-----|------|-----------|
| `twitch_client_id` | Twitch Client ID | "" |
| `deepl_api_key` | DeepL API Key | "" |
| `gladia_api_key` | Gladia API Key | "" |
| `channel_name` | チャンネル名 | "" |
| `translate_mode` | 翻訳モード | "自動" |
| `commands_enabled` | コマンド機能の有効/無効 | true |
| `voicevox_speaker_id` | ボイスID | 14 |
| `voicevox_auto_start` | VOICEVOX自動起動 | true |
| `ui_theme` | UIテーマ | "default" |
| `log_level` | ログレベル | "INFO" |
| `bits_sound_path` | Bits効果音パス | "" |
| `bits_sound_volume` | Bits効果音音量 | 80 |
| `chat_log_history_limit` | ログ履歴の上限 | 1000 |
| `participant_limit` | 参加者数の上限 | 1000 |
| `auto_restart_enabled` | メモリ超過時の自動再起動 | false |
| `auto_restart_threshold_mb` | 自動再起動の閾値(MB) | 1000 |
| `auto_update_check` | 起動時のアップデート確認 | true |

</details>

## ログファイル

ログは `dist/logs/bot_YYYY-MM-DD.log` に出力されます。
- 日付ごとにローテーション
- 7日間保持

## トラブルシューティング

### VOICEVOX に接続できない

1. VOICEVOX Engineが起動していることを確認
2. 設定パネルで「接続テスト」を実行
3. ファイアウォールでポート50021が許可されていることを確認

### 翻訳されない

1. DeepL API Keyが正しく設定されていることを確認
2. 「チャット翻訳」トグルがオンになっていることを確認
3. 翻訳フィルターに該当していないことを確認

### 音声認識が動作しない

1. マイクが正しく選択されていることを確認
2. Gladia API Keyが設定されていることを確認（または Google SR を使用）
3. マイクのアクセス権限を確認

### メモリ使用量が増え続ける

1. `config.json`の`auto_restart_enabled`を`true`に設定すると閾値超過時に自動再起動
2. ログ履歴上限は`chat_log_history_limit`で調整可能（デフォルト1000）
3. `scripts/profile_app.py cpu`でCPUプロファイリングが可能

## ライセンス

MIT License

## 貢献

Issues や Pull Requests を歓迎します。
