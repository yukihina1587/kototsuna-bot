# Issue #41: OBS WebSocket連携 設計メモ

## 目的
- OBSの配信状態/シーンに応じて、ことつなBOTの動作を自動制御する。

## 追加した設計
- `src/obs_integration.py`
  - `ObsController`: OBS WebSocketへ接続し、配信状態と現在シーンを監視。
  - `find_matching_scene_rule`: シーン名に一致するルール選択。
- `src/config.py`
  - OBS設定キーを追加し、`validate_config` で型/範囲/ルール正規化を実施。
- `src/gui.py`
  - 起動時に `ObsController` を初期化（`obs_enabled=true` 時のみ開始）。
  - 配信開始検知で `start_bot()`、配信終了検知で `stop_bot()` を実行。
  - シーンルールに応じてTTSミュート/解除、およびソース表示制御を適用。
  - 終了処理で OBS コントローラーを停止。

## 設定キー
- `obs_enabled`: OBS連携の有効/無効
- `obs_host`, `obs_port`, `obs_password`: OBS WebSocket接続情報
- `obs_poll_interval_sec`: 監視ポーリング間隔
- `obs_auto_control_enabled`: OBS連動の自動制御ON/OFF
- `obs_auto_start_bot`: 配信開始時BOT起動
- `obs_auto_stop_bot`: 配信終了時BOT停止
- `obs_scene_rules`: シーン別ルール
  - 例:
  ```json
  [
    {
      "scene": "休憩",
      "tts_mute": true,
      "show_sources": ["BreakCard"],
      "hide_sources": ["AlertOverlay"]
    }
  ]
  ```

## 実装範囲（今回）
- 配信開始/終了の自動制御
- シーン変更時の TTS ミュート制御
- シーン変更時のソース表示/非表示制御（ルールベース）

## 今後の拡張候補
- GUI設定タブにOBS接続設定とシーンルール編集UIを追加
- ポーリングに加え、イベント購読方式を選択可能にする
- 「特定イベント時に一時ソース表示」などのタイマー制御
