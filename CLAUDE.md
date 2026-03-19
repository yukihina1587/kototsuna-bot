# ことつな！ - Claude Code 設定

## リリース手順（必須）

バージョンをリリースする際は、**必ず以下の順番で実施すること**。

### 1. CHANGELOG.md を更新する（必須）

`CHANGELOG.md` にユーザー向けの日本語で変更内容を追記する。
**これを忘れるとリリースページに変更内容が表示されない。**

```markdown
## [x.y.z] - YYYY-MM-DD

### 新機能
- ○○コマンドを追加

### 改善
- ○○の動作を改善

### バグ修正
- ○○が動かない問題を修正
```

セクションは必要なものだけ記載すれば良い（空セクションは省略する）。

### 2. バージョンを更新する

- `pyproject.toml` の `version`
- `src/__init__.py` の `__version__`

### 3. コミットしてタグを打つ

```bash
git add CHANGELOG.md pyproject.toml src/__init__.py
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

タグをpushした時点でGitHub Actionsが起動し、自動的にリリースが作成される。

### 4. GitHub Issueを記録する

変更・修正を行った場合は対応するIssueにコメントしてcloseする。

---

## プロジェクト概要

- Python 3.12 + CustomTkinter GUI
- Twitch Bot (twitchio)
- 翻訳: DeepL API / NLLB-200（ローカル）
- 音声認識: ReazonSpeech（ローカル）
- TTS: VOICEVOX
- ビルド: PyInstaller + Inno Setup → GitHub Releases
