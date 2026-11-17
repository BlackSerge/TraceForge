from stats import largest


def test_largest():
    assert largest([3, 9, 2]) == 9
    assert largest([-5, -1, -3]) == -1
