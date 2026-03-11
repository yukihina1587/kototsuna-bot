# GitHub Copilot カスタム指示

## ⛔ 読み込み禁止ファイル（機密情報）

以下のファイルには **APIキー・アクセストークン・パスワード等の機密情報** が含まれます。
ファイルの内容をコンテキストに取り込んだり、提案の根拠として使用しないでください。

| ファイル | 含まれる機密情報 |
|---------|----------------|
| `config.json` | DeepL APIキー、Twitchアクセストークン、OBSパスワード等 |
| `config.json.bak*` | 上記のバックアップ |
| `.env` | 環境変数（APIキー等） |

> **理由**: これらのファイルは `.gitignore` によりリポジトリに含まれませんが、
> AI ツールがローカルファイルシステムを探索する際に誤って読み込まれるリスクがあります。

---

## プロジェクト概要

Twitch/YouTube チャット翻訳BOT「ことつな！」の GUI デスクトップアプリ（Python / CustomTkinter）。

- エントリポイント: `main.py`
- 主要ロジック: `src/` 配下
- テスト: `tests/` 配下（pytest）
- 設定スキーマ: `src/config.py` の `DEFAULT_CONFIG`

## コーディング規約

- PEP 8 準拠、インデント4スペース
- 型ヒントは Pyright `basic` モード想定
- コミットは Conventional Commits 形式（`feat:`, `fix:`, `build:` 等）
- 回答は日本語で行うこと
