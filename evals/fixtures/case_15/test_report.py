from report import summarize


def test_summarize():
    assert summarize([2, 4, 6]) == {'count': 3, 'mean': 4}
