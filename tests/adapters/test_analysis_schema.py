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


def test_comparison_uses_filtered_filler_counts() -> None:
    output = make_output(
        comparison=ComparisonOut(fixed=["in"], regressed=[], adopted_suggestions=[])
    )
    analysis = output.to_domain(TRANSCRIPT, previous_filler_count=5)
    assert analysis.comparison is not None
    assert analysis.comparison.fillers_before == 5
    assert analysis.comparison.fillers_after == 1
