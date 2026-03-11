# Repository Guidelines

## プロジェクト構成

- `main.py` はGUIアプリの起動とBOTの初期化を担当します。
- `src/` に主要ロジックを配置しています（認証、翻訳、TTS、GUI、オーバーレイ）。
- `tests/` は `pytest` のテスト置き場です。
- `assets/` は画像などのUIリソースを格納します。
- `build/` と `dist/` はPyInstallerの生成物です（手動で編集しません）。
- `config.json` と `tts_dictionary.json` は実行時の設定/辞書データです。
- `overlay.html` と `redirect.html` は認証/オーバーレイ用の静的ページです。

## ビルド・テスト・開発コマンド

- `uv sync --group dev` 全依存関係（開発ツール含む）をインストールします。
- `uv sync` 本番依存のみインストールします。
- `python main.py` GUIアプリを起動します。
- `pytest` テストを実行します（`pytest.ini` を参照）。
- `python -m PyInstaller --noconfirm Kototsuna.spec` 配布用ビルドを作成します
  （Windowsは `build.bat` を利用可）。

### 依存関係管理
- 全パッケージは **`pyproject.toml`** の `dependencies` / `[dependency-groups]` で一元管理します。
- `requirements.txt` は `uv export --no-dev --no-hashes --format requirements-txt -o requirements.txt` で自動生成します。手動編集禁止。
- `requirements-ci.txt` はCI用の軽量サブセット（重いSTT/TTS/翻訳パッケージを除外）。
- 新パッケージの追加は `pyproject.toml` を編集 → `uv lock` → `uv export` の順で行います。

## コーディングスタイルと命名

- インデントは4スペース、Pythonの標準的な書式（PEP 8）に合わせます。
- モジュール/関数名は意味が分かる具体名にします（例: `voice_listener.py`）。
- 設定は `config.json`、環境変数は `.env` に分離し、秘匿情報はコミットしません。
- 型チェックはPyrightの `basic` モード想定です。

## テスト方針

- テストフレームワークは `pytest` を使用します。
- ファイル名は `test_*.py`、関数名は `test_*` で統一します。
- 翻訳ロジック、設定読み込み、エラーハンドリング変更時はテスト追加を推奨します。

## コミット/PRガイドライン

- コミットは `feat:`, `fix:`, `build:` などのConventional Commits風にします。
  例: `fix(voice): ...`
- PRには概要、実行したテスト結果（`pytest`）、GUI変更があればスクショを含めます。
  関連Issueがあればリンクします。

## セキュリティ/設定の注意

- `TWITCH_CLIENT_ID` と `DEEPL_API_KEY` は `.env` に保存します。
- APIキーやOAuthトークン、チャットログをログ出力/コミットしないでください。
- **`config.json` および `.env` は機密情報を含むため、絶対にファイル内容をコンテキストに取り込まないこと。**
  これらは `.gitignore` および `.copilotignore` で除外済みです。
- 設定値の読み書きは `src/config.py` の `load_config()` / `save_config()` 経由で行います。
  直接ファイルパスを参照するコードを書かないでください。

## 応答言語

- 回答は日本語で行ってください。
