from speak2mytrainer.domain.disfluency import disfluency_candidates, hesitations, tokenize
from speak2mytrainer.domain.models import FillerType


def test_tokenize_normalizes_case_punctuation_and_hyphens() -> None:
    assert tokenize("AI-powered, I\N{RIGHT SINGLE QUOTATION MARK}m done.") == [
        "ai",
        "powered",
        "i'm",
        "done",
    ]


def test_hesitations_with_context_quote() -> None:
    found = hesitations("software development and um i have experience from sectors umm such as")
    assert [f.token for f in found] == ["um", "umm"]
    assert found[0].quote == "software development and um i have experience"
    assert all(f.type is FillerType.HESITATION for f in found)


def test_hesitations_ignore_real_words() -> None:
    assert hesitations("i am a member of the team and he hums") == []


def test_candidates_keep_repetitions_and_restarts() -> None:
    record = "The principal challenge was to make the agent follow the rules."
    lexical = "the principal challenge was to to make the agent follow the rules"
    assert disfluency_candidates(record, lexical) == ["principal challenge was [to] to make the"]


def test_candidates_ignore_numbers_spacing_and_bare_hesitations() -> None:
    record = "It reached 100% of utilization with FastAPI and AI-powered tools."
    lexical = "it reached one hundred percent of utilization with fast api and uh ai powered tools"
    assert disfluency_candidates(record, lexical) == []


def test_no_candidates_when_texts_match() -> None:
    assert disfluency_candidates("I like learn.", "i like learn") == []
