import pytest

from spain_libraries_mcp.queries import SearchCriteria, to_cql, to_pqf


def test_criteria_items_and_normalization():
    c = SearchCriteria(
        title="  Don Quijote  ",
        author="   ",
        isbn="978-84-376-0494-7",
        subject="Novel",
        text="\t",
    )
    assert c.items() == [
        ("isbn", "9788437604947"),
        ("title", "Don Quijote"),
        ("subject", "Novel"),
    ]
    assert not c.is_empty()
    assert c.summary() == "9788437604947 Don Quijote Novel"


def test_criteria_isbn_only_hyphens_is_empty():
    c = SearchCriteria(isbn="--- - ---")
    assert c.items() == []
    assert c.is_empty()
    with pytest.raises(ValueError):
        to_pqf(c)


def test_criteria_isbn10_with_x():
    c = SearchCriteria(isbn="84-376-0494-X")
    assert c.items() == [("isbn", "843760494X")]


def test_pqf_variants_and_extra():
    c = SearchCriteria(title="Rayuela", author="Cortázar")
    assert to_pqf(c, variant=0, extra="@attr 3=3") == (
        '@and @attr 1=4 @attr 3=3 @attr 4=6 "Rayuela" '
        '@attr 1=1003 @attr 3=3 @attr 4=6 "Cortázar"'
    )
    assert to_pqf(c, variant=1, extra="@attr 3=3") == (
        '@and @attr 1=4 @attr 4=6 "Rayuela" '
        '@attr 1=1003 @attr 4=6 "Cortázar"'
    )
    assert to_pqf(c, variant=2, extra="@attr 3=3") == (
        '@and @attr 1=4 "Rayuela" '
        '@attr 1=1003 "Cortázar"'
    )


def test_pqf_escapes_quotes_and_backslashes():
    c = SearchCriteria(text=r'a\b "c"')
    assert to_pqf(c, variant=2) == r'@attr 1=1016 "a\\b \"c\""'


def test_pqf_isbn_skips_extra_and_wordlist():
    c = SearchCriteria(isbn="9788437604947")
    assert to_pqf(c, variant=0, extra="@attr 3=3") == '@attr 1=7 "9788437604947"'
    assert to_pqf(c, variant=1) == '@attr 1=7 "9788437604947"'
    assert to_pqf(c, variant=2) == '@attr 1=7 "9788437604947"'


def test_cql_indices_and_fallback():
    indices = {"title": "alma.title", "text": "alma.all_for_ui"}
    c = SearchCriteria(title='El "Quijote"', author="Cervantes")
    assert to_cql(c, indices) == 'alma.title="El Quijote" and alma.all_for_ui="Cervantes"'


def test_cql_fails_without_valid_indices():
    with pytest.raises(ValueError):
        to_cql(SearchCriteria(author="Cervantes"), {"title": "alma.title"})
    with pytest.raises(ValueError):
        to_cql(SearchCriteria(), {"title": "alma.title"})
