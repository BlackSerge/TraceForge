from lists import flatten


def test_flatten():
    assert flatten([1, [2, [3, [4]]]]) == [1, 2, 3, 4]
    assert flatten([]) == []
