# はじめに

## 動作環境

- **OS**: Windows 10/11、macOS、Linux
- **Python**: 3.10以上（3.12推奨）
- **メモリ**: 4GB以上推奨

## インストール

### 1. リポジトリのクローン

```bash
git clone https://github.com/yukihina1587/kototsuna-bot.git
cd kototsuna-bot
```

### 2. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 3. 必要な設定情報の取得

#### Twitch Client ID

1. [Twitch Developers](https://dev.twitch.tv/console)にアクセス
2. 「アプリケーション」→「アプリケーションを登録」
3. 以下を入力:
   - **名前**: 任意（例: `MyTranslateBot`）
   - **OAuthリダイレクトURL**: `http://localhost:8787/redirect.html`
   - **カテゴリ**: `チャットボット`
4. 作成後、**クライアントID**をコピー

### 4. 起動

```bash
python main.py
```

## 初回設定

1. GUIが起動したら、右パネルの「設定」を開く
2. **Twitch Client ID**を入力
3. **トークン認証**ボタンをクリック
4. ブラウザでTwitch認証を完了
5. **チャンネル名**を入力
6. **BOT起動**ボタンをクリック

## オプション設定

### VOICEVOX（高品質読み上げ）

1. [VOICEVOX公式サイト](https://voicevox.hiroshiba.jp/)からダウンロード
2. インストール・起動
3. GUIの設定パネルでパスを設定（自動検出も可能）

### ローカル翻訳

- 翻訳はローカルエンジン固定です
- DeepL API Key の取得や設定は不要です

## 次のステップ

- [機能一覧](Features)で詳細な機能を確認
- [設定](Configuration)でカスタマイズ
