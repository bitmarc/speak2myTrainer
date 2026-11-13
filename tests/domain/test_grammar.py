from speak2mytrainer.domain.grammar import soften_colloquial
from speak2mytrainer.domain.models import GrammarIssue, Severity


def _error(quote: str, fix: str) -> GrammarIssue:
    return GrammarIssue(quote=quote, fix=fix, why="", severity=Severity.ERROR)


def test_prescriptive_corrections_become_suggestions() -> None:
    issues = soften_colloquial(
        [
            _error("If I was you, I'd ask", "If I were you, I'd ask"),
            _error("Less people came", "Fewer people came"),
            _error("There's a lot of reasons", "There are a lot of reasons"),
        ]
    )
    assert [i.severity for i in issues] == [Severity.SUGGESTION] * 3


def test_real_errors_stay_errors() -> None:
    issues = soften_colloquial(
        [
            _error("If I was you, I'd asked", "If I were you, I'd ask"),  # dos cambios
            _error("she don't", "she doesn't"),
            _error("more easy", "easier"),
        ]
    )
    assert [i.severity for i in issues] == [Severity.ERROR] * 3


def test_fixes_that_only_remove_disfluencies_are_not_grammar() -> None:
    from speak2mytrainer.domain.grammar import is_disfluency_fix

    assert is_disfluency_fix(
        _error("We, um, we migrated the, the system", "We migrated the system")
    )
    assert not is_disfluency_fix(_error("we build the system", "we built the system"))
    assert not is_disfluency_fix(_error("the system", "the system"))
