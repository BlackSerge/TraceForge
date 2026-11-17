from words import word_count


def test_word_count():
    assert word_count('a b a') == {'a': 2, 'b': 1}
    assert word_count('') == {}
