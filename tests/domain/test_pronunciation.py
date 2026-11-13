from speak2mytrainer.domain.models import PronunciationIssue
from speak2mytrainer.domain.pronunciation import (
    MAX_ISSUES,
    aligned_word_indexes,
    grounded_issues,
)


def _issue(word: str, index: int, score: float = 40.0) -> PronunciationIssue:
    return PronunciationIssue(
        word=word, score=score, error_type="Mispronunciation", word_index=index
    )


def test_aligned_words_skip_misrecognitions() -> None:
    record = "It was a conversational agent based on RAG architecture."
    words = ["it", "was", "a", "conversational", "agent", "based", "on", "rock", "architecture"]
    assert aligned_word_indexes(record, words) == {0, 1, 2, 3, 4, 5, 6, 8}


def test_aligned_words_need_every_token() -> None:
    assert aligned_word_indexes("We use FastAPI.", ["we", "use", "fast-api"]) == {0, 1}


def test_grounded_issues_filter_dedupe_and_sort() -> None:
    record = "I developed the agent and developed the RAG search."
    words = ["i", "developed", "the", "agent", "and", "developed", "the", "rock", "search"]
    issues = [
        _issue("developed", 1, 55),
        _issue("rock", 7, 20),
        _issue("developed", 5, 46),
        _issue("agent", 3, 50),
        PronunciationIssue(word="search", score=10, error_type="LowAccuracy"),
    ]
    shown = grounded_issues(record, words, issues)
    assert [(i.word, i.score) for i in shown] == [("developed", 46), ("agent", 50)]


def test_grounded_issues_cap() -> None:
    words = [f"w{i}" for i in range(20)]
    issues = [_issue(w, i, float(i)) for i, w in enumerate(words)]
    shown = grounded_issues(" ".join(words), words, issues)
    assert len(shown) == MAX_ISSUES
    assert shown[0].word == "w0"
