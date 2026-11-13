from speak2mytrainer.domain.disfluency import (
    combine_fillers,
    disfluency_candidates,
    hesitations,
    repetitions,
    tokenize,
)
from speak2mytrainer.domain.models import Filler, FillerType


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


def test_repetitions_count_the_discarded_copy() -> None:
    found = repetitions("so we solved it to to make the rules or or flow")
    assert [f.token for f in found] == ["to", "or"]
    assert found[0].quote == "we solved it to to make the rules"
    assert all(f.type is FillerType.RESTART for f in found)


def test_repetitions_across_hesitations_phrases_and_cut_words() -> None:
    lexical = "after um after a feature i have i have the constraint constraints valid validates"
    assert [f.token for f in repetitions(lexical)] == ["after", "i have", "constraint", "valid"]


def test_repetitions_keep_grammatical_doubles() -> None:
    assert repetitions("i think that that is true and he had had enough very very good") == []
    assert [f.token for f in repetitions("a problem that uh that was")] == ["that"]


def test_repetitions_ignore_short_prefixes() -> None:
    assert repetitions("it was on only one server in into") == []


def test_combine_fillers_drops_llm_duplicates_of_python_repetitions() -> None:
    llm = [
        Filler(quote="and and you know", token="and and", type=FillerType.RESTART),
        Filler(quote="and and you know", token="you know", type=FillerType.LEXICAL),
        Filler(quote="um so", token="um", type=FillerType.HESITATION),
        Filler(quote="um so the", token="Um", type=FillerType.LEXICAL),  # mal tipado
    ]
    combined = combine_fillers("um so the implementation and and you know", llm)
    assert [(f.token, f.type) for f in combined] == [
        ("um", FillerType.HESITATION),
        ("and", FillerType.RESTART),
        ("you know", FillerType.LEXICAL),
    ]
