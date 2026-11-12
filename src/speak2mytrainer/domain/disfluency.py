"""Disfluencias a partir de las dos transcripciones del ADR 0002.

- Las hesitaciones (um, uh, eh, hmm...) se detectan en la forma léxica de Speech con una regex:
  Python las cuenta, el LLM no.
- Lo demás que Speech oyó y el texto de registro limpió (repeticiones, reinicios, "and" sueltos)
  sale de alinear ambos textos y se entrega al LLM como candidatos; el LLM decide.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from speak2mytrainer.domain.models import Filler, FillerType

# um, umm, uh, uhm, eh, erm, hmm, ah, em, mm...
HESITATION_RE = re.compile(r"^(?:u+m+|u+h+m*|e+h+|e+r+m*|h+u*m+|a+h+|e+m+|m{2,})$")

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_CONTEXT_WORDS = 3


def tokenize(text: str) -> list[str]:
    """Minúsculas y sin puntuación; "AI-powered" y "AI powered" dan los mismos tokens."""
    return _TOKEN_RE.findall(text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'"))


def _window(tokens: list[str], start: int, end: int) -> tuple[str, str]:
    before = " ".join(tokens[max(start - _CONTEXT_WORDS, 0) : start])
    after = " ".join(tokens[end : end + _CONTEXT_WORDS])
    return before, after


def hesitations(lexical: str) -> list[Filler]:
    """Una muletilla de pausa por cada hesitación del texto léxico, con su contexto como cita."""
    tokens = tokenize(lexical)
    found: list[Filler] = []
    for i, token in enumerate(tokens):
        if HESITATION_RE.match(token):
            before, after = _window(tokens, i, i + 1)
            quote = " ".join(part for part in (before, token, after) if part)
            found.append(Filler(quote=quote, token=token, type=FillerType.HESITATION))
    return found


def disfluency_candidates(record_text: str, lexical: str) -> list[str]:
    """Fragmentos que Speech oyó y el texto de registro no tiene, con contexto: "a [b c] d".

    Se ignoran las hesitaciones (ya contadas), las diferencias de números ("100" frente a
    "one hundred percent") y las de espacios ("fastapi" frente a "fast api").
    """
    ref = tokenize(record_text)
    hyp = tokenize(lexical)
    candidates: list[str] = []
    matcher = SequenceMatcher(None, ref, hyp, autojunk=False)
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op not in ("insert", "replace") or (b2 - b1) <= (a2 - a1):
            continue
        ref_part, hyp_part = ref[a1:a2], hyp[b1:b2]
        if any(t.isdigit() for t in ref_part) or "".join(ref_part) == "".join(hyp_part):
            continue
        inserted = [t for t in hyp_part if not HESITATION_RE.match(t)]
        if not inserted:
            continue
        before, after = _window(hyp, b1, b2)
        candidates.append(" ".join(p for p in (before, f"[{' '.join(hyp_part)}]", after) if p))
    return candidates
