from age import is_adult


def test_is_adult():
    assert is_adult(18) is True
    assert is_adult(17) is False
    assert is_adult(30) is True
