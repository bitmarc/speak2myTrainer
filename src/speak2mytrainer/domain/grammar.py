"""Reglas deterministas sobre la gramática que devuelve el LLM.

El PRD pide juzgar inglés conversacional: ciertas correcciones son prescriptivas y nunca deben
salir como Error, aunque el modelo insista. Si la ÚNICA diferencia entre la cita y la corrección
es uno de estos cambios, la severidad baja a Sugerencia (se sigue mostrando).
"""

from __future__ import annotations

from difflib import SequenceMatcher

from speak2mytrainer.domain.disfluency import HESITATION_RE, tokenize
from speak2mytrainer.domain.models import GrammarIssue, Severity

# (lo que dijo, la corrección prescriptiva) en tokens.
COLLOQUIAL_CHANGES: frozenset[tuple[tuple[str, ...], tuple[str, ...]]] = frozenset(
    {
        (("was",), ("were",)),  # if I was you
        (("less",), ("fewer",)),  # less people
        (("there's",), ("there", "are")),  # there's a lot of reasons
        (("there's",), ("there're",)),
        (("who",), ("whom",)),
        (("me", "and", "my"), ("my",)),  # me and my team → my team and I
        (("me",), ("i",)),
        (("their",), ("his", "or", "her")),
        (("they",), ("he", "or", "she")),
    }
)


def _only_colloquial(quote: str, fix: str) -> bool:
    before, after = tokenize(quote), tokenize(fix)
    changes = [
        (tuple(before[a1:a2]), tuple(after[b1:b2]))
        for op, a1, a2, b1, b2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
        if op != "equal"
    ]
    return bool(changes) and all(change in COLLOQUIAL_CHANGES for change in changes)


def _fluent(tokens: list[str]) -> list[str]:
    """Sin hesitaciones y sin palabras repetidas seguidas."""
    words = [t for t in tokens if not HESITATION_RE.match(t)]
    return [w for i, w in enumerate(words) if i == 0 or w != words[i - 1]]


def is_disfluency_fix(issue: GrammarIssue) -> bool:
    """La corrección solo quita "um" o repeticiones: es una muletilla, no un error gramatical."""
    before, after = tokenize(issue.quote), tokenize(issue.fix)
    return before != after and _fluent(before) == _fluent(after)


def soften_colloquial(issues: list[GrammarIssue]) -> list[GrammarIssue]:
    """Baja a Sugerencia los "errores" cuya única corrección es prescriptiva."""
    for issue in issues:
        if issue.severity is Severity.ERROR and _only_colloquial(issue.quote, issue.fix):
            issue.severity = Severity.SUGGESTION
    return issues
