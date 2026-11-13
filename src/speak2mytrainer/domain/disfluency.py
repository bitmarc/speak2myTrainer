"""Disfluencias a partir de las dos transcripciones del ADR 0002.

- Las hesitaciones (um, uh, eh, hmm...) se detectan en la forma léxica de Speech con una regex:
  Python las cuenta, el LLM no.
- Las repeticiones inmediatas ("to to", "after um after", "valid validates") también las cuenta
  Python: son reinicios evidentes y el LLM las pasa por alto con frecuencia.
- Lo demás que Speech oyó y el texto de registro limpió (repeticiones, reinicios, "and" sueltos)
  sale de alinear ambos textos y se entrega al LLM como candidatos; el LLM decide.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from speak2mytrainer.domain.models import Filler, FillerType

# um, umm, uh, uhm, eh, erm, hmm, ah, em, mm...
HESITATION_RE = re.compile(r"^(?:u+m+|u+h+m*|e+h+|e+r+m*|h+u*m+|a+h+|e+m+|m{2,})$")

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_CONTEXT_WORDS = 3
# Palabras que pueden repetirse seguidas con sentido: "had had", "that that", "very very".
# Con una hesitación en medio ("that uh that") sí son un reinicio.
_VALID_DOUBLES = frozenset({"had", "that", "very", "really", "no", "yes", "yeah", "bye", "ha"})
# Palabra cortada y retomada: "valid validates", "constraint constraints"; "on only" no cuenta.
_MIN_PARTIAL = 4
_MAX_PHRASE = 3  # "i have i have"


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


def _repeat_length(words: list[tuple[int, str]], k: int) -> int:
    """Longitud de la frase que empieza en `k` y se repite justo después; 0 si no se repite."""
    for n in range(1, _MAX_PHRASE + 1):
        first = [t for _, t in words[k : k + n]]
        second = [t for _, t in words[k + n : k + 2 * n]]
        if len(second) < n:
            break
        if first == second:
            adjacent = words[k + 1][0] == words[k][0] + 1
            if n == 1 and adjacent and first[0] in _VALID_DOUBLES:
                continue
            return n
        if n == 1 and len(first[0]) >= _MIN_PARTIAL and second[0].startswith(first[0]):
            return 1
    return 0


def repetitions(lexical: str) -> list[Filler]:
    """Un reinicio por cada palabra o frase del texto léxico que se repite en seguida.

    Las hesitaciones intermedias no cortan la repetición ("after um after"). El token es la
    copia descartada (la primera) y la cita, ambas copias con su contexto.
    """
    tokens = tokenize(lexical)
    words = [(i, t) for i, t in enumerate(tokens) if not HESITATION_RE.match(t)]
    found: list[Filler] = []
    k = 0
    while k < len(words):
        n = _repeat_length(words, k)
        if not n:
            k += 1
            continue
        start, end = words[k][0], words[k + 2 * n - 1][0] + 1
        before, after = _window(tokens, start, end)
        quote = " ".join(p for p in (before, " ".join(tokens[start:end]), after) if p)
        token = " ".join(t for _, t in words[k : k + n])
        found.append(Filler(quote=quote, token=token, type=FillerType.RESTART))
        k += n
    return found


def _filler_key(token: str) -> str:
    words = tokenize(token)
    return " ".join(w for i, w in enumerate(words) if i == 0 or w != words[i - 1])


def combine_fillers(lexical: str, llm_fillers: list[Filler]) -> list[Filler]:
    """Hesitaciones y repeticiones de Python más los reinicios y muletillas léxicas del LLM.

    Si el LLM también reporta una repetición que Python ya contó, se descarta la del LLM.
    """
    found = hesitations(lexical) + repetitions(lexical)
    pending = Counter(_filler_key(f.token) for f in found if f.type is FillerType.RESTART)
    for filler in llm_fillers:
        if filler.type is FillerType.HESITATION:
            continue
        key = _filler_key(filler.token)
        if pending[key] > 0:
            pending[key] -= 1
            continue
        found.append(filler)
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
