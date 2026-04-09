# API参照

## オーバーレイサーバー

BOT起動時に自動的にHTTPサーバーが起動し、オーバーレイ用のAPIを提供します。

### サーバー情報

- **デフォルトポート**: 8080
- **ポート自動検索**: 8080が使用中の場合、上位ポートを探索
- **プロトコル**: HTTP

### エンドポイント

#### GET /api/current

現在の翻訳テキストを取得します。

**レスポンス例**:
```json
{
  "text": "Hello → こんにちは",
  "id": 42
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `text` | string | 翻訳テキスト |
| `id` | number | 更新ID（変更検知用） |

#### GET /api/history

翻訳履歴を取得します（最新50件）。

**レスポンス例**:
```json
[
  {
    "original": "Hello everyone",
    "translated": "皆さんこんにちは",
    "username": "user123",
    "timestamp": "2026-01-31T10:30:00.000Z"
  },
  ...
]
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `original` | string | 原文 |
| `translated` | string | 翻訳文 |
| `username` | string | ユーザー名 |
| `timestamp` | string | タイムスタンプ（ISO 8601） |

#### GET /overlay.html

オーバーレイ用のHTMLページを取得します。

---

## OBSでの使用方法

### ブラウザソースの追加

1. OBSで「ソース」→「+」→「ブラウザ」
2. 以下を設定:
   - **URL**: `http://localhost:8080/overlay.html`
   - **幅**: 800（任意）
   - **高さ**: 200（任意）
   - **カスタムCSS**: 必要に応じて調整

### カスタムCSS例

```css
body {
  background-color: transparent !important;
}

.translation-text {
  font-size: 24px;
  color: white;
  text-shadow: 2px 2px 4px black;
}
```

---

## ポーリングによる更新検知

オーバーレイは `/api/current` をポーリングして更新を検知できます。

```javascript
let lastId = 0;

setInterval(async () => {
  const response = await fetch('http://localhost:8080/api/current');
  const data = await response.json();

  if (data.id !== lastId) {
    lastId = data.id;
    // 新しい翻訳を表示
    displayTranslation(data.text);
  }
}, 1000); // 1秒ごとにチェック
```

---

## CORSについて

すべてのエンドポイントで `Access-Control-Allow-Origin: *` ヘッダーが設定されているため、任意のドメインからアクセス可能です。

---

## 内部関数

### update_translation(original, translated, username)

翻訳データを更新します。

```python
from src.overlay_server import update_translation

update_translation("Hello", "こんにちは", "user123")
```

### start_server(port=8080)

オーバーレイサーバーを起動します。

### stop_server()

オーバーレイサーバーを停止します。

### run_server_thread(port=8080)

バックグラウンドスレッドでサーバーを起動します。
