from text import count_vowels


def test_count_vowels():
    assert count_vowels('Apple') == 2
    assert count_vowels('xyz') == 0
    assert count_vowels('AEIOU') == 5
