from src.auth import check_missing_scopes, SCOPES


def test_check_missing_scopes_none_missing():
    assert check_missing_scopes(SCOPES) == []


def test_check_missing_scopes_all_missing():
    assert check_missing_scopes([]) == SCOPES


def test_check_missing_scopes_partial():
    partial = ['chat:read', 'chat:edit']
    missing = check_missing_scopes(partial)
    assert 'chat:read' not in missing
    assert 'chat:edit' not in missing
    assert len(missing) == len(SCOPES) - 2
