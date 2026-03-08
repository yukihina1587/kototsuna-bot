import threading
import time
from typing import Any, Callable, Optional

from src.logger import logger


def find_matching_scene_rule(scene_name: str, rules: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """シーン名に一致する最初のルールを返す（大文字小文字を無視）。"""
    normalized = (scene_name or "").strip().lower()
    if not normalized:
        return None
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("scene", "")).strip().lower()
        if name and name == normalized:
            return rule
    return None


class ObsController:
    """OBS WebSocket 連携。

    接続時に EventClient（WebSocketイベント購読）を優先し、
    失敗した場合はポーリングにフォールバックする。
    ReqClient はソース表示制御などのリクエスト用に常時保持する。
    """

    def __init__(
        self,
        config_getter: Callable[[], dict[str, Any]],
        on_stream_state_change: Optional[Callable[[bool], None]] = None,
        on_scene_change: Optional[Callable[[str], None]] = None,
        on_connection_change: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._config_getter = config_getter
        self._on_stream_state_change = on_stream_state_change
        self._on_scene_change = on_scene_change
        self._on_connection_change = on_connection_change

        self._running = False
        self._worker: Optional[threading.Thread] = None
        self._client: Any = None           # ReqClient（リクエスト用）
        self._event_client: Any = None     # EventClient（イベント購読用）
        self._using_events: bool = False   # イベント購読が有効か
        self._connected = False
        self._lock = threading.Lock()
        self._last_stream_active: Optional[bool] = None
        self._last_scene_name: Optional[str] = None
        self._missing_dependency_logged = False

    @property
    def using_events(self) -> bool:
        """イベント購読方式が有効かどうか。"""
        return self._using_events and self._is_event_client_alive()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run_loop, daemon=True, name="obs-controller")
        self._worker.start()
        logger.info("[OBS] Controller started.")

    def stop(self) -> None:
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        self._disconnect()
        logger.info("[OBS] Controller stopped.")

    def _run_loop(self) -> None:
        while self._running:
            cfg = self._config_getter() or {}
            if not cfg.get("obs_enabled", False):
                self._disconnect()
                time.sleep(1.0)
                continue

            interval = self._clamp_float(cfg.get("obs_poll_interval_sec", 1.0), 1.0, 0.2, 10.0)
            try:
                req_client = self._ensure_req_client(cfg)

                # EventClient が切断されていたらリセット
                if self._using_events and not self._is_event_client_alive():
                    logger.warning("[OBS] Event client disconnected, falling back to polling.")
                    self._disconnect_event_client()

                # EventClient 未接続なら接続を試みる
                if not self._using_events:
                    self._try_connect_event_client(cfg)

                # イベント未使用時はポーリングで状態変化を検知
                # イベント使用中はポーリングを接続死活確認として実行（状態変化はイベントが担う）
                self.poll_once(req_client)

            except ImportError:
                if not self._missing_dependency_logged:
                    logger.warning("[OBS] obsws-python が未インストールのため OBS 連携を無効化します。")
                    self._missing_dependency_logged = True
                self._running = False
                break
            except Exception as e:
                logger.warning(f"[OBS] Polling error: {e}")
                self._disconnect()
                time.sleep(max(interval, 1.0))
                continue

            time.sleep(interval)

    def poll_once(self, client: Any = None) -> None:
        """現在のOBS状態を1回取得してイベント差分を通知する（テスト用に公開）。

        イベント購読が有効な場合、すでにイベントで状態が更新されているため
        通常は差分が検出されずコールバックは呼ばれない（接続死活確認として機能）。
        """
        req_client = client or self._client
        if req_client is None:
            return

        stream_active = self._fetch_stream_active(req_client)
        with self._lock:
            if self._last_stream_active is None:
                self._last_stream_active = stream_active
                fire_stream = False
            elif stream_active != self._last_stream_active:
                self._last_stream_active = stream_active
                fire_stream = True
            else:
                fire_stream = False
        if fire_stream and self._on_stream_state_change:
            self._on_stream_state_change(stream_active)

        scene_name = self._fetch_scene_name(req_client)
        if scene_name:
            with self._lock:
                if self._last_scene_name is None:
                    self._last_scene_name = scene_name
                    fire_scene = False
                elif scene_name != self._last_scene_name:
                    self._last_scene_name = scene_name
                    fire_scene = True
                else:
                    fire_scene = False
            if fire_scene and self._on_scene_change:
                self._on_scene_change(scene_name)

    def set_source_visible(self, source_name: str, visible: bool, scene_name: Optional[str] = None) -> bool:
        """現在シーンまたは指定シーンでソース表示状態を切り替える。"""
        with self._lock:
            req_client = self._client
        if req_client is None:
            return False

        scene = scene_name or self._fetch_scene_name(req_client)
        if not scene:
            return False

        scene_item_id = self._resolve_scene_item_id(req_client, scene, source_name)
        if scene_item_id is None:
            return False

        try:
            self._call_method(
                req_client,
                "set_scene_item_enabled",
                scene_name=scene,
                scene_item_id=scene_item_id,
                scene_item_enabled=visible,
            )
            return True
        except Exception:
            try:
                self._call_method(
                    req_client,
                    "set_scene_item_enabled",
                    sceneName=scene,
                    sceneItemId=scene_item_id,
                    sceneItemEnabled=visible,
                )
                return True
            except Exception as e:
                logger.warning(f"[OBS] Failed to set source visibility ({source_name}): {e}")
                return False

    # ------------------------------------------------------------------
    # 接続管理
    # ------------------------------------------------------------------

    def _ensure_req_client(self, cfg: dict[str, Any]) -> Any:
        """ReqClient を返す。未接続なら接続する。"""
        with self._lock:
            if self._client is not None:
                return self._client

        try:
            import obsws_python
        except ImportError as e:
            raise ImportError from e

        host = str(cfg.get("obs_host", "127.0.0.1")).strip() or "127.0.0.1"
        port = self._clamp_int(cfg.get("obs_port", 4455), 4455, 1, 65535)
        password = str(cfg.get("obs_password", ""))

        client = obsws_python.ReqClient(host=host, port=port, password=password, timeout=3)
        self._call_method(client, "get_version")

        with self._lock:
            self._client = client
        self._set_connected(True)
        logger.info(f"[OBS] Connected to OBS WebSocket (ReqClient): {host}:{port}")
        return client

    def _try_connect_event_client(self, cfg: dict[str, Any]) -> bool:
        """EventClient（WebSocketイベント購読）への接続を試みる。

        成功すると self._using_events = True になり、
        配信状態・シーン変更が即座にコールバックで通知される。
        失敗した場合はポーリングにフォールバックする。
        """
        with self._lock:
            if self._event_client is not None:
                return True

        try:
            import obsws_python
        except ImportError:
            return False

        host = str(cfg.get("obs_host", "127.0.0.1")).strip() or "127.0.0.1"
        port = self._clamp_int(cfg.get("obs_port", 4455), 4455, 1, 65535)
        password = str(cfg.get("obs_password", ""))

        try:
            event_client = obsws_python.EventClient(host=host, port=port, password=password, timeout=3)

            def on_stream_state_changed(data: Any) -> None:
                active = bool(getattr(data, "output_active", False))
                with self._lock:
                    if self._last_stream_active == active:
                        return
                    self._last_stream_active = active
                logger.debug(f"[OBS] Stream state event: active={active}")
                if self._on_stream_state_change:
                    self._on_stream_state_change(active)

            def on_current_program_scene_changed(data: Any) -> None:
                scene = (getattr(data, "scene_name", "") or "").strip()
                if not scene:
                    return
                with self._lock:
                    if self._last_scene_name == scene:
                        return
                    self._last_scene_name = scene
                logger.debug(f"[OBS] Scene change event: {scene}")
                if self._on_scene_change:
                    self._on_scene_change(scene)

            event_client.callback.register([
                on_stream_state_changed,
                on_current_program_scene_changed,
            ])

            with self._lock:
                self._event_client = event_client
            self._using_events = True
            logger.info(f"[OBS] Event subscription established: {host}:{port}")
            return True

        except Exception as e:
            logger.debug(f"[OBS] Event subscription failed, using polling: {e}")
            return False

    def _is_event_client_alive(self) -> bool:
        """EventClient の内部スレッドが生存しているか確認する。"""
        with self._lock:
            ec = self._event_client
        if ec is None:
            return False
        worker = getattr(ec, "worker", None)
        return worker is not None and worker.is_alive()

    def _disconnect_event_client(self) -> None:
        """EventClient のみ切断する。"""
        with self._lock:
            ec = self._event_client
            self._event_client = None
        self._using_events = False
        if ec is not None:
            try:
                ec.disconnect()
            except Exception:
                pass

    def _disconnect(self) -> None:
        """ReqClient と EventClient の両方を切断する。"""
        self._disconnect_event_client()
        with self._lock:
            client = self._client
            self._client = None
        if client is not None:
            try:
                if hasattr(client, "disconnect") and callable(client.disconnect):
                    client.disconnect()
            except Exception:
                pass
        self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        if self._connected == connected:
            return
        self._connected = connected
        if self._on_connection_change:
            self._on_connection_change(connected)

    # ------------------------------------------------------------------
    # OBS API ヘルパー
    # ------------------------------------------------------------------

    def _fetch_stream_active(self, req_client: Any) -> bool:
        resp = self._call_method(req_client, "get_stream_status")
        for key in ("output_active", "outputActive", "active"):
            value = getattr(resp, key, None)
            if isinstance(value, bool):
                return value
        if isinstance(resp, dict):
            for key in ("output_active", "outputActive", "active"):
                value = resp.get(key)
                if isinstance(value, bool):
                    return value
        return False

    def _fetch_scene_name(self, req_client: Any) -> str:
        resp = self._call_method(req_client, "get_current_program_scene")
        for key in ("current_program_scene_name", "currentProgramSceneName", "scene_name", "sceneName"):
            value = getattr(resp, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(resp, dict):
            for key in ("current_program_scene_name", "currentProgramSceneName", "scene_name", "sceneName"):
                value = resp.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _resolve_scene_item_id(self, req_client: Any, scene_name: str, source_name: str) -> Optional[int]:
        try:
            resp = self._call_method(req_client, "get_scene_item_id", scene_name=scene_name, source_name=source_name)
        except Exception:
            try:
                resp = self._call_method(req_client, "get_scene_item_id", sceneName=scene_name, sourceName=source_name)
            except Exception as e:
                logger.warning(f"[OBS] Failed to resolve scene item ID ({source_name} in {scene_name}): {e}")
                return None

        for key in ("scene_item_id", "sceneItemId"):
            value = getattr(resp, key, None)
            if isinstance(value, int):
                return value
        if isinstance(resp, dict):
            for key in ("scene_item_id", "sceneItemId"):
                value = resp.get(key)
                if isinstance(value, int):
                    return value
        return None

    @staticmethod
    def _call_method(client: Any, method_name: str, **kwargs: Any) -> Any:
        method = getattr(client, method_name, None)
        if method is None or not callable(method):
            raise AttributeError(f"OBS client does not support method: {method_name}")
        return method(**kwargs)

    @staticmethod
    def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, parsed))

    @staticmethod
    def _clamp_float(value: Any, default: float, min_value: float, max_value: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, parsed))
