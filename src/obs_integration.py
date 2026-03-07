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
    """OBS WebSocket 連携（ポーリングベース）。"""

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
        self._client: Any = None
        self._connected = False
        self._lock = threading.Lock()
        self._last_stream_active: Optional[bool] = None
        self._last_scene_name: Optional[str] = None
        self._missing_dependency_logged = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run_loop, daemon=True, name="obs-controller")
        self._worker.start()
        logger.info("OBS controller started.")

    def stop(self) -> None:
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        self._disconnect()
        logger.info("OBS controller stopped.")

    def _run_loop(self) -> None:
        while self._running:
            cfg = self._config_getter() or {}
            if not cfg.get("obs_enabled", False):
                self._disconnect()
                time.sleep(1.0)
                continue

            interval = self._clamp_float(cfg.get("obs_poll_interval_sec", 1.0), 1.0, 0.2, 10.0)
            try:
                client = self._ensure_client(cfg)
                self.poll_once(client)
            except ImportError:
                if not self._missing_dependency_logged:
                    logger.warning("obsws-python が未インストールのため OBS 連携を無効化します。")
                    self._missing_dependency_logged = True
                self._running = False
                break
            except Exception as e:
                logger.warning(f"OBS polling error: {e}")
                self._disconnect()
                time.sleep(max(interval, 1.0))
                continue

            time.sleep(interval)

    def poll_once(self, client: Any = None) -> None:
        """現在のOBS状態を1回取得してイベント差分を通知する（テスト用に公開）。"""
        req_client = client or self._client
        if req_client is None:
            return

        stream_active = self._fetch_stream_active(req_client)
        if self._last_stream_active is None:
            self._last_stream_active = stream_active
        elif stream_active != self._last_stream_active:
            self._last_stream_active = stream_active
            if self._on_stream_state_change:
                self._on_stream_state_change(stream_active)

        scene_name = self._fetch_scene_name(req_client)
        if scene_name:
            if self._last_scene_name is None:
                self._last_scene_name = scene_name
            elif scene_name != self._last_scene_name:
                self._last_scene_name = scene_name
                if self._on_scene_change:
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
                logger.warning(f"Failed to set source visibility ({source_name}): {e}")
                return False

    def _ensure_client(self, cfg: dict[str, Any]) -> Any:
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
        logger.info(f"Connected to OBS WebSocket: {host}:{port}")
        return client

    def _disconnect(self) -> None:
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
                logger.warning(f"Failed to resolve scene item ID ({source_name} in {scene_name}): {e}")
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
