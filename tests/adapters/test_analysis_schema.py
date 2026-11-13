from speak2mytrainer.adapters.outbound.azure_openai.schema import (
    AnalysisOutput,
    ComparisonOut,
    FillerOut,
    GrammarOut,
    ValidNonFillerOut,
)
from speak2mytrainer.domain.models import FillerType, Severity

TRANSCRIPT = (
    "well i once participated on a project where we build a eemm a system based on a RAG "
    "architecture. So the client needed to manage users"
)


def make_output(**overrides: object) -> AnalysisOutput:
    data: dict[str, object] = {
        "fillers": [FillerOut(quote="we build a eemm a system", token="eemm", type="hesitation")],
        "valid_non_fillers": [
            ValidNonFillerOut(quote="So the client needed", token="So", reason="connector")
        ],
        "grammar": [
            GrammarOut(
                quote="participated on a project",
                fix="participated in a project",
                why="...",
                severity="error",
            )
        ],
        "improved_version": "Well, I once took part in a project...",
        "next_steps": ["a", "b", "c"],
        "comparison": None,
    }
    data.update(overrides)
    return AnalysisOutput.model_validate(data)


def test_translates_to_domain() -> None:
    analysis = make_output().to_domain(TRANSCRIPT)
    assert analysis.fillers[0].type is FillerType.HESITATION
    assert analysis.grammar[0].severity is Severity.ERROR
    assert analysis.valid_non_fillers[0].token == "So"
    assert analysis.comparison is None


def test_drops_quotes_not_in_transcript() -> None:
    output = make_output(
        fillers=[
            FillerOut(quote="you know, it was", token="you know", type="lexical"),
            FillerOut(quote="we build a eemm a", token="eemm", type="hesitation"),
        ],
        grammar=[GrammarOut(quote="I has a doubt", fix="I have", why="...", severity="error")],
    )
    analysis = output.to_domain(TRANSCRIPT)
    assert [f.token for f in analysis.fillers] == ["eemm"]
    assert analysis.grammar == []


def test_drops_filler_whose_token_is_not_in_quote() -> None:
    output = make_output(fillers=[FillerOut(quote="based on a RAG", token="like", type="lexical")])
    assert output.to_domain(TRANSCRIPT).fillers == []


def test_occurrence_in_both_lists_counts_as_valid() -> None:
    output = make_output(
        fillers=[FillerOut(quote="well i once participated", token="well", type="lexical")],
        valid_non_fillers=[
            ValidNonFillerOut(quote="Well, I once participated", token="Well", reason="opener")
        ],
    )
    analysis = output.to_domain(TRANSCRIPT)
    assert analysis.fillers == []
    assert len(analysis.valid_non_fillers) == 1


def test_quote_matching_ignores_case_and_punctuation() -> None:
    output = make_output(
        fillers=[FillerOut(quote="We build a, eemm... a system", token="Eemm", type="hesitation")]
    )
    assert len(output.to_domain(TRANSCRIPT).fillers) == 1


def test_comparison_only_with_previous_attempt() -> None:
    output = make_output(
        comparison=ComparisonOut(fixed=["in"], regressed=[], adopted_suggestions=[])
    )
    assert output.to_domain(TRANSCRIPT).comparison is None
    analysis = output.to_domain(TRANSCRIPT, has_previous=True)
    assert analysis.comparison is not None
    assert analysis.comparison.fixed == ["in"]


RECORD = "The principal challenge was to make the agent follow the rules. We solved it."
VERBATIM = "the principal challenge was to to make the agent follow the rules we solve it"


def test_restart_quote_can_come_from_verbatim() -> None:
    output = make_output(
        fillers=[FillerOut(quote="was to to make", token="to", type="restart")],
        valid_non_fillers=[],
        grammar=[],
    )
    assert output.to_domain(RECORD).fillers == []
    assert [f.token for f in output.to_domain(RECORD, VERBATIM).fillers] == ["to"]


def test_grammar_quote_must_come_from_record_text() -> None:
    # "we solve it" solo existe en la forma léxica de Speech: no puede ser un error gramatical.
    output = make_output(
        fillers=[],
        valid_non_fillers=[],
        grammar=[GrammarOut(quote="we solve it", fix="we solved it", why="...", severity="error")],
    )
    assert output.to_domain(RECORD, VERBATIM).grammar == []


def test_next_steps_are_capped_at_three() -> None:
    output = make_output(next_steps=["1", "2", "3", "4", "5"])
    assert output.to_domain(TRANSCRIPT).next_steps == ["1", "2", "3"]
