"""Palabras con problema de pronunciación que se pueden mostrar sin riesgo (ADR 0003).

La evaluación no guionizada marca también palabras que Speech reconoció mal ("rock" por "RAG",
"kaaba"): mostrarlas sería un falso positivo. Solo se conserva una palabra marcada si la
alineación con el texto de registro la empareja con la misma palabra.
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from speak2mytrainer.domain.disfluency import tokenize
from speak2mytrainer.domain.models import PronunciationIssue

MAX_ISSUES = 8


def aligned_word_indexes(record_text: str, words: list[str]) -> set[int]:
    """Índices de `words` cuyos tokens coinciden todos (`equal`) con el texto de registro."""
    ref = tokenize(record_text)
    hyp: list[str] = []
    owner: list[int] = []
    for i, word in enumerate(words):
        for token in tokenize(word):
            hyp.append(token)
            owner.append(i)
    total = Counter(owner)
    matched: Counter[int] = Counter()
    for op, _, _, b1, b2 in SequenceMatcher(None, ref, hyp, autojunk=False).get_opcodes():
        if op == "equal":
            matched.update(owner[b1:b2])
    return {i for i, n in total.items() if matched[i] == n}


def grounded_issues(
    record_text: str, words: list[str], issues: list[PronunciationIssue]
) -> list[PronunciationIssue]:
    """Las palabras marcadas que el texto de registro confirma, peores primero, sin repetir la
    misma palabra (se queda su peor ocurrencia) y como máximo `MAX_ISSUES`."""
    aligned = aligned_word_indexes(record_text, words)
    worst: dict[str, PronunciationIssue] = {}
    for issue in issues:
        if issue.word_index is None or issue.word_index not in aligned:
            continue
        key = issue.word.lower()
        if key not in worst or issue.score < worst[key].score:
            worst[key] = issue
    return sorted(worst.values(), key=lambda i: i.score)[:MAX_ISSUES]
