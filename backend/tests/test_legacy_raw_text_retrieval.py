import pytest

from app.services.retrieval import _text_overlap_score


@pytest.mark.parametrize(
    ("query", "text"),
    [
        ("", "linear algebra"),
        ("linear algebra", ""),
        ("", ""),
    ],
)
def test_text_overlap_score_returns_zero_for_empty_input(query: str, text: str) -> None:
    assert _text_overlap_score(query, text) == 0.0


def test_text_overlap_score_uses_lowercase_character_jaccard() -> None:
    # {a, b, c} intersect {b, c, d}, divided by their four-character union.
    assert _text_overlap_score("ABC", "bcd") == pytest.approx(0.5)
