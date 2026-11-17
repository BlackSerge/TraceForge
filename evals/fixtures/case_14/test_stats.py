from stats import average


def test_average():
    assert average([2, 4]) == 3
    assert average([]) == 0
