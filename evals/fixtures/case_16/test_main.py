from main import checkout


def test_checkout_total():
    assert checkout([(10, 2), (5, 1)]) == 25
    assert checkout([]) == 0
