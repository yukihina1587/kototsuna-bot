# ことつな！ - Twitch翻訳BOT

Twitchのチャットメッセージをリアルタイムで翻訳するBOTです。

## 概要

- **DeepL API**を使用した高品質な翻訳
- **VOICEVOX**による日本語読み上げ
- **Gladia API**によるリアルタイム音声認識
- Twitchイベント（フォロー、サブスク、Bits等）の検知と通知
- **OBS WebSocket 連携**：配信開始/終了で BOT を自動制御、シーンルール対応
- **字幕オーバーレイ**：音声翻訳をリアルタイム字幕として OBS に表示

## クイックスタート

1. [セットアップガイド](Getting-Started)を参照してインストール
2. Twitch Client IDとDeepL API Keyを取得
3. `python main.py` で起動
4. GUIで認証してBOTを開始

## ドキュメント

| ページ | 内容 |
|-------|------|
| [はじめに](Getting-Started) | インストールと初期設定 |
| [機能一覧](Features) | すべての機能の詳細 |
| [OBS連携](OBS-Setup) | ブラウザソース・WebSocket連携の設定 |
| [設定](Configuration) | 設定項目の説明 |
| [パフォーマンス](Performance) | メモリ管理・最適化・プロファイリング |
| [トラブルシューティング](Troubleshooting) | よくある問題と解決方法 |
| [API参照](API-Reference) | オーバーレイAPIの仕様 |

## 必要なもの

- Python 3.10以上（3.12推奨）
- Twitchアカウント
- DeepL APIキー（Free版可）
- VOICEVOX Engine（オプション）
- Gladia APIキー（オプション）

## リンク

- [GitHub リポジトリ](https://github.com/yukihina1587/kototsuna-bot)
- [Issues（バグ報告・機能要望）](https://github.com/yukihina1587/kototsuna-bot/issues)
