# ことつな！ - Twitch翻訳BOT

[![Tests](https://github.com/yukihina1587/kototsuna-bot/actions/workflows/test.yml/badge.svg)](https://github.com/yukihina1587/kototsuna-bot/actions/workflows/test.yml)

Twitchのチャットメッセージをリアルタイムで翻訳するBOTです。ローカル翻訳エンジンと、VOICEVOXによる読み上げ機能を搭載しています。

## 主な機能

### チャット翻訳
- 日本語⇔英語の双方向自動翻訳（ローカル翻訳）
- 翻訳モード選択（自動 / 英→日 / 日→英）
- 翻訳のオン/オフ切り替え
- 翻訳フィルター（特定ワードをスキップ）
- カスタム辞書（翻訳前の置換）

### 音声機能
- **チャット読み上げ（TTS）**: VOICEVOXによる高品質な音声読み上げ
  - 複数のボイスから選択可能
  - VOICEVOX未起動時はpyttsx3にフォールバック
- **音声翻訳（マイク入力）**: マイクに向かって喋った内容を翻訳
  - ローカル音声認識（ReazonSpeech-k2-v2）

### Twitchイベント検知
- **フォロー通知**: EventSub WebSocketで検知
- **サブスク通知**: 新規サブスク、継続サブスク
- **ギフトサブ通知**: ギフトサブ、ミステリーギフト
- **Bits（チア）通知**: 金額とメッセージ表示
- **イベント効果音**: 各イベントに個別の効果音を設定可能（ボリューム調整付き）

### チャットHTML出力（OBS連携）
- **OBSブラウザソース対応**: チャットログをHTMLファイルとして出力し、OBSのブラウザソースで直接読み込み可能
- **サードパーティエモート**: BTTV / FFZ / 7TV のエモートを画像として表示
- **自動更新**: HTMLファイルは自動的に更新され、OBS側でリアルタイム反映
- **簡易プレビュー**: アプリ内でテキストベースの簡易プレビューを表示

### その他の機能
- **オーバーレイサーバー**: OBS等で使用可能な翻訳オーバーレイ
- **参加者追跡**: キーワード検知で参加者を自動登録
- **チャットコマンド**: `!help`, `!translate`等のビルトインコマンド + カスタムコマンド
- **読み上げ辞書**: 漢字の読み間違いを修正
- **UIテーマ**: 4種類のテーマから選択可能
- **ログレベル切り替え**: DEBUG/INFO/WARNING/ERRORの動的切り替え
- **API安定性**: ネットワークエラー時の自動リトライ（指数バックオフ）
- **パフォーマンス最適化**: 翻訳バッチ処理、GUI差分更新、メモリ自動制限
- **自動アップデート**: GitHub Releasesからの自動更新チェック
- **軽量な配布**: 不要なブラウザエンジンを排除し、EXEサイズを大幅削減

## 必要なもの

- Python 3.10以上（3.12推奨）
- Twitchアカウント
- マイク（音声翻訳機能を使用する場合）
- VOICEVOX Engine（高品質な読み上げを使用する場合、オプション）

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

### 3. VOICEVOX Engineのインストール（オプション）

1. [VOICEVOX公式サイト](https://voicevox.hiroshiba.jp/)からダウンロード
2. インストール後、起動（デフォルト: `http://localhost:50021`）

**フォールバック**: VOICEVOX未起動時は自動的にpyttsx3にフォールバックします。

### 4. 実行

```bash
python main.py
```

## 使い方

### 初回起動時

1. **Twitch Client ID**を設定パネルに入力
2. **トークン認証**ボタンをクリック → ブラウザでTwitch認証
3. **チャンネル名**を入力（または認証アカウントと同じを選択）
4. **BOT起動**ボタンをクリック

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
| 翻訳設定 | ローカル翻訳固定 |
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

1. ローカル翻訳モデルが配置されていることを確認
2. 「チャット翻訳」トグルがオンになっていることを確認
3. 翻訳フィルターに該当していないことを確認

### 音声認識が動作しない

1. マイクが正しく選択されていることを確認
2. マイクのアクセス権限を確認
3. ローカル音声認識モデルが配置されていることを確認

### メモリ使用量が増え続ける

1. `config.json`の`auto_restart_enabled`を`true`に設定すると閾値超過時に自動再起動
2. ログ履歴上限は`chat_log_history_limit`で調整可能（デフォルト1000）
3. `scripts/profile_app.py cpu`でCPUプロファイリングが可能

## プラグイン（わんコメ互換）

ことつなはわんコメ互換の JavaScript プラグイン (`plugin.js`) に対応しています。  
Node.js がインストールされていれば、わんコメ用に作られたプラグインをそのまま利用できます。

### プラグインの配置

```
%APPDATA%\Kototsuna\plugins\{plugin-name}\plugin.js
```

フォルダを作成して `plugin.js` を配置するだけで、BOT 起動時に自動的に読み込まれます。

### 対応フック

| フック | 説明 |
|--------|------|
| `init({ dir, store }, initialData)` | 起動時に1回呼ばれる |
| `filterComment(comment, service, userData)` | コメントごとに呼ばれる。`false` を返すとブロック、変更したオブジェクトを返すと変換 |
| `subscribe(type, data)` | コメントイベント通知 (`type='comments'`) |
| `destroy()` | 停止時に呼ばれる |

### サンプル plugin.js

```javascript
const plugin = {
  name: 'My Plugin',
  uid: 'com.example.myplugin',
  version: '1.0.0',
  author: 'YourName',
  permissions: ['comments'],

  init({ dir, store }, initialData) {},
  destroy() {},

  filterComment(comment, service, userData) {
    // NGワードをブロック
    if (comment.data.comment.includes('NG')) return false
    return comment
  },

  subscribe(type, ...args) {
    if (type === 'comments') {
      const { comments } = args[0]
      // 全コメントを受信
    }
  },
}
module.exports = plugin
```

### 注意

- Node.js が必要です（[nodejs.org](https://nodejs.org/)）
- `store` は `%APPDATA%\Kototsuna\plugin-store\{uid}.json` に永続化されます

## プライバシー / クラッシュレポート

不具合修正のため、ことつな！は**任意で**クラッシュレポートを送信できます（オプトイン制、デフォルトは送信しない）。

- 何が送信され、何が送信されないかは [docs/PRIVACY.md](docs/PRIVACY.md) を参照してください
- 設定パネルの「プライバシー」セクションでいつでも有効化／無効化できます
- チャンネル名・コメント本文・トークン等の個人情報は送信されません

## ライセンス

MIT License

## 貢献

Issues や Pull Requests を歓迎します。
