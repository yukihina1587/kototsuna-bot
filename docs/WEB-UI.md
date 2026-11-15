# 単一ウィンドウの配信ワークスペース（Issue #214）

Windowsでは、ことつな！を1回起動すると新しい操作画面が1つ開きます。翻訳・音声・Twitch/OBS処理も同時に起動します。別のターミナルやブラウザを起動して管理する必要はありません。

- [Issue #214](https://github.com/yukihina1587/kototsuna-bot/issues/214)
- ブランチ: `feature/214-local-web-ui`、起点: 公開版v1.9.3
- ローカル開発版。公開リリース・自動更新への収録はまだ行っていません。

## 起動と終了

```powershell
python -m pip install -r requirements.txt
python main.py
```

WindowsのWebView2 Runtimeを使用します。`--web-ui` でも同じ単一画面になります。認証時だけ、通常のブラウザにTwitchの認証画面が開きます。

ウィンドウを閉じると、BOT・マイク・読み上げ・管理サーバー・表示用プロセスも終了します。配信中は最小化してください。OBSの操作ドックを閉じても、アプリは終了しません。

従来画面は `python main.py --legacy-ui` で起動できます。Linux/macOSの通常起動も従来画面のままです。`--legacy-ui --web-ui` は従来のブラウザ併用モードです。

## スタジオとフォーカス

標準の「スタジオ」は、上部に接続状態と開始・停止、左に目的別ナビ、中央にチャット、右に日常の操作をまとめています。「フォーカス」へ切り替えるとチャットが横に広がり、操作が下部にまとまります。選択は `web_workspace_layout` として保存し、再起動後にも引き継ぎます。

音声・字幕・OBS・接続設定は右側のパネルで開き、チャットを見ながら編集できます。分類を切り替えても入力途中の内容は保持します。Escまたは閉じるボタンで配信コントロールに戻り、未保存なら破棄を確認します。字幕は色・サイズ・縁取り・表示対象を縮小サンプルで確認できます（実配信の映像ではありません）。

マイクのメーターは実際の入力の目安を表示します。認識・翻訳中と読み上げ中は処理側の状態に連動し、マイク停止・入力途絶・通信断では古いメーターを残しません。新着コメントの短いアニメーションは、OSの「動きを減らす」設定に従います。

## 配信の準備

1. 左の「設定」→「設定・Twitch接続」でチャンネルを指定し、「変更を保存」を押します。
2. 「Twitchに接続」でブラウザ認証を完了します。配布版は同梱Client IDを使えます。ソース実行では環境変数または接続設定にClient IDが必要です。
3. 音声タブでエンジン・マイクを設定します。保存後に一覧を更新し、ボイスを選んで保存・試聴できます。
4. メイン画面でBOTを開始し、必要に応じてチャット翻訳・マイク翻訳・読み上げをONにします。
5. OBSへ表示する場合は左の「OBS」から「コメント表示URL」をブラウザソースに貼り付けます。

設定は接続・音声・表示・効果音・字幕・OBS連携・管理に分かれています。変更は保存時に反映します。入力途中の内容は定期更新で上書きせず、閉じる際は未保存の変更を確認します。

フォレスト・ミニマル・グラデーション・サイバーパンクの4テーマはすぐに画面全体へ反映し、既存の `ui_theme` 設定で次回起動にも引き継ぎます。

OBSパスワードは取得APIで返さず、空欄のまま保存した場合は既存の値を維持します。Twitchトークンも画面へ返しません。接続中のチャンネル変更、マイク稼働中の入力デバイス変更は停止を案内します。

音量は再生中のpygame音声にも反映します。速度は次の合成から反映し、既に合成済みの音声は作り直しません。pyttsx3では次の発話から反映します。

## OBSの操作ドック（任意）

| 用途 | コピーするURL | OBSの設定先 |
| --- | --- | --- |
| 原文・翻訳を配信映像へ表示 | コメント表示URL | ブラウザソース |
| OBS内からアプリを操作 | 操作パネルURL | カスタムブラウザドック |

操作ドックは約360px幅を想定しています。操作URLはアプリ起動中のみ有効です。再起動時はURLをコピーし直してください。操作用資格情報を含むため共有しないでください。

## 実装と依存

- `desktop_window.py`: 表示用WebViewプロセスの起動・監視・終了。URLは匿名パイプで渡し、引数やファイルへ記録しません。親プロセス終了時はパイプのEOFで表示側も終了します。
- `web_desktop_app.py`: 既存のTk状態管理を非表示で再利用し、Web画面から設定・認証・音声・更新を操作します。認証や機器取得はワーカースレッド、結果の反映はTkスレッドで行います。
- `web_settings.py`: 設定の許可リストと型・範囲・URLの検証。設定全体や秘密情報は公開しません。
- `desktop_web_ui.py` / `web_control.py`: 安全なスナップショットと上限16件の操作キュー。タイムアウトした未実行の操作は破棄します。
- `web_ui.py`: aiohttpを使用し127.0.0.1の空きポートで管理画面を提供。ランダムな認証情報、Host/Origin検証、CSP、no-store、no-referrerを適用します。既存OBS表示サーバーとは分離しています。
- `web_ui_assets/`: ビルド不要のHTML/CSS/JavaScript。コメントはtextContentで描画します。
- `auth.py`: コールバック受信開始後にブラウザを開き、認証試行ごとのstate、Host/Origin、本文サイズを検証。5分で待機を終了し、トークンをログに記録しません。

表示用依存に **pywebview 6.2.1（BSD 3-Clause）** をWindows限定で追加しました。TkとWebViewが両方メインスレッドを必要とするためプロセスを分けています。表示プロセスはアプリの寿命に結び付け、ユーザーが別途起動する常駐サービスにはしません。

[pywebviewの依存条件](https://pywebview.flowrl.com/guide/installation.html)、[ライセンス・配布情報](https://pypi.org/project/pywebview/)、[MicrosoftのWebView2配布ガイド](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。インストーラーは署名を確認したMicrosoft公式Bootstrapperを同梱し、WebView2未導入時だけ実行します（インターネット接続が必要）。導入に失敗した場合は既存アプリの置換前に停止します。スタートメニューには従来画面のショートカットも用意します。

## 検証

```bash
python -m pytest tests/ -q --ignore=tests/test_tts.py --ignore=tests/test_bot.py
node --check src/web_ui_assets/app.js
```

Windowsの実Tk設定連携:

```powershell
$env:KOTOTSUNA_GUI_TESTS="1"
python -m pytest tests/test_gui_workspace.py -q
```

実ブラウザとWebViewの確認（テスト用状態・一時プロファイルを使用し、Twitch接続や音声再生は行いません）:

```powershell
python tests/web_ui_browser_check.py --chromium "C:\Program Files\Google\Chrome\Application\chrome.exe"
python tests/desktop_window_check.py
# PyInstallerで作成したEXEの表示プロセスも同じ条件で確認可能
python tests/desktop_window_check.py --executable build/desktop-package/Kototsuna/Kototsuna.exe
```

画面・設定・4テーマ・再読み込み・ドック同期・表示停止・狭い幅・Enter/Esc・HTML文字列・通信断を検証します。スクリーンショットは `build/web-ui-previews/` に保存します。WebView検証は可視ウィンドウが1つであること、ウィンドウを閉じた際と親側終了の両方で表示プロセスが終了することを確認します。

## 今回の検証結果（2026-11-15）

- CIと同じ対象: **530 passed / 90 skipped**。ディスプレイ・ネイティブ依存が必要なテスト等はスキップ。
- WindowsのGUI・設定・BOT・更新・Web・音声関連413ケース: 初回411成功、既存音声テスト2件が環境依存で失敗。実モデルに依存していたテストをモック化し、固定スラッシュの期待値をOS標準に修正。修正後の音声関連は **38 passed**、失敗2件も成功を確認（その他は初回の成功を採用）。
- Windows Chrome: スタジオ／フォーカスと再読み込み後の保持、7分類の設定と入力保持、字幕サンプル、4テーマ、780×620の主要操作、390px幅、360pxのOBSドック同期、表示停止、Enter/Escとフォーカス復帰、XSS対策、通信断を確認。
- 入力メーターは合成音声サンプルで反応・無音・入力途絶・停止を検証。読み上げ状態は実デバイスを使わず通常終了と例外経路を検証。
- Windows WebView2: 新しいPyInstaller EXEで可視画面1つ、HTML/JS/API接続、画面を閉じた時と親側終了の両方の終了に成功。
- PyInstallerビルド成功。NLLB翻訳・ReazonSpeech・Silero VADを同梱。HTML/CSS/JSが作業ソースと同一であることをハッシュで確認。出力は `build/desktop-package/Kototsuna/`。
- Python/JavaScript構文、HTMLのID重複、差分の空白チェックに成功。追加依存なし。
- 実アカウントでのTwitch接続・OBS操作・マイク録音や実音声再生、インストーラー、自動更新の適用は未実施。既に起動中の開発アプリは再起動していない。新UIは既存画面を閉じてから開発版を起動する。

## 移行の範囲と残り

日常の接続・音声・字幕・OBS・管理設定は新しい画面から操作できます。辞書編集、参加者・常連・独自コマンド・プラグイン管理、OBSシーンルール編集、カスタムテーマ作成などの専用パネルは従来画面に残っています。既存データと処理は保持しています。

GUIに依存しない処理サービスへの完全な分離、OBSドックの再起動後のペアリング、実Twitch/OBS/マイクを使う配信テスト、モデル同梱インストーラーと自動更新経由の検証は継続作業です。

## v1.10.0の配布

公開タグのGitHub Actionsでテスト・モデル同梱ビルド・Inno Setupコンパイルを行い、まずドラフトを作成します。配布物のSHA256とWebView起動を確認してから正式版として公開します。既存自動更新のアセット名 `Kototsuna_Setup.exe` と設定の保存先を維持します。

WebView2の導入は [Microsoftの配布手順](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution) に従います。既に導入済みなら追加実行しません。
