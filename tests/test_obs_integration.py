from src.obs_integration import ObsController, find_matching_scene_rule


class _Resp:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeClient:
    def __init__(self):
        self.stream_states = [False, True]
        self.scenes = ["待機", "休憩"]
        self._i = 0
        self.calls = []

    def get_stream_status(self):
        idx = min(self._i, len(self.stream_states) - 1)
        return _Resp(output_active=self.stream_states[idx])

    def get_current_program_scene(self):
        idx = min(self._i, len(self.scenes) - 1)
        self._i += 1
        return _Resp(current_program_scene_name=self.scenes[idx])

    def get_scene_item_id(self, scene_name, source_name):
        self.calls.append(("get_scene_item_id", scene_name, source_name))
        return _Resp(scene_item_id=7)

    def set_scene_item_enabled(self, scene_name, scene_item_id, scene_item_enabled):
        self.calls.append(("set_scene_item_enabled", scene_name, scene_item_id, scene_item_enabled))


class _ErrorClient:
    """全メソッドが例外を送出するクライアント（エラーパステスト用）。"""

    def get_scene_item_id(self, **kwargs):
        raise RuntimeError("source not found")

    def set_scene_item_enabled(self, **kwargs):
        raise RuntimeError("unexpected")


def test_find_matching_scene_rule_case_insensitive():
    rules = [{"scene": "休憩", "tts_mute": True}]
    matched = find_matching_scene_rule("休憩", rules)
    assert matched is not None
    assert matched["tts_mute"] is True


def test_find_matching_scene_rule_no_match():
    rules = [{"scene": "休憩", "tts_mute": True}]
    assert find_matching_scene_rule("本番", rules) is None


def test_find_matching_scene_rule_none_input():
    rules = [{"scene": "休憩", "tts_mute": True}]
    assert find_matching_scene_rule(None, rules) is None  # type: ignore[arg-type]
    assert find_matching_scene_rule("", rules) is None


def test_find_matching_scene_rule_invalid_rule_entries():
    rules = ["invalid", None, {"scene": "休憩", "tts_mute": True}]
    matched = find_matching_scene_rule("休憩", rules)
    assert matched is not None and matched["tts_mute"] is True


def test_poll_once_emits_state_changes():
    stream_events = []
    scene_events = []
    ctrl = ObsController(
        config_getter=lambda: {},
        on_stream_state_change=lambda v: stream_events.append(v),
        on_scene_change=lambda v: scene_events.append(v),
    )
    client = _FakeClient()
    ctrl.poll_once(client)  # baseline
    ctrl.poll_once(client)  # change
    assert stream_events == [True]
    assert scene_events == ["休憩"]


def test_set_source_visible_calls_obs_methods():
    ctrl = ObsController(config_getter=lambda: {})
    client = _FakeClient()
    ctrl._client = client
    ok = ctrl.set_source_visible("Alert", True, scene_name="休憩")
    assert ok is True
    assert ("get_scene_item_id", "休憩", "Alert") in client.calls
    assert ("set_scene_item_enabled", "休憩", 7, True) in client.calls


def test_set_source_visible_returns_false_when_source_not_found():
    """存在しないソース名を指定しても False を返し、例外を送出しないこと。"""
    ctrl = ObsController(config_getter=lambda: {})
    ctrl._client = _ErrorClient()
    ok = ctrl.set_source_visible("NonexistentSource", True, scene_name="休憩")
    assert ok is False


def test_set_source_visible_returns_false_when_no_client():
    ctrl = ObsController(config_getter=lambda: {})
    ok = ctrl.set_source_visible("Alert", True, scene_name="休憩")
    assert ok is False


def test_resolve_scene_item_id_returns_none_on_error():
    """両方のAPIフォームが失敗した場合 None を返すこと。"""
    ctrl = ObsController(config_getter=lambda: {})
    result = ctrl._resolve_scene_item_id(_ErrorClient(), "休憩", "MissingSource")
    assert result is None
