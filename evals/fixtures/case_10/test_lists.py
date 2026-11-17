from lists import total


def test_total():
    assert total([1, 2, 3]) == 6
    assert total([5]) == 5
