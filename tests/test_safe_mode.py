from src.safe_mode import (
    should_offer_post_update_rollback,
    should_suggest_safe_mode,
)


def test_should_suggest_safe_mode_matches_crash_threshold():
    assert should_suggest_safe_mode(1) is False
    assert should_suggest_safe_mode(2) is True


def test_should_offer_post_update_rollback_requires_all_conditions():
    assert should_offer_post_update_rollback(2, True, True) is True
    assert should_offer_post_update_rollback(1, True, True) is False
    assert should_offer_post_update_rollback(2, False, True) is False
    assert should_offer_post_update_rollback(2, True, False) is False
