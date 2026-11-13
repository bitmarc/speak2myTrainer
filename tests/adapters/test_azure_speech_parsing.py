"""Lectura del JSON detallado de Speech, sin llamar al servicio."""

from typing import Any

import pytest

pytest.importorskip("azure.cognitiveservices.speech")

from speak2mytrainer.adapters.outbound.azure_speech import _pronunciation, _verbatim


def _word(text: str, offset: int, accuracy: float, error: str = "None") -> dict[str, Any]:
    return {
        "Word": text,
        "Offset": offset * 10_000_000,
        "Duration": 5_000_000,
        "PronunciationAssessment": {"AccuracyScore": accuracy, "ErrorType": error},
        "Phonemes": [
            {"Phoneme": "e", "PronunciationAssessment": {"AccuracyScore": 90}},
            {"Phoneme": "m", "PronunciationAssessment": {"AccuracyScore": 20}},
        ],
    }


def _segment(words: list[dict[str, Any]], pron: float, prosody: float | None) -> dict[str, Any]:
    scores = {"PronScore": pron, "AccuracyScore": pron, "FluencyScore": pron}
    if prosody is not None:
        scores["ProsodyScore"] = prosody
    return {
        "NBest": [
            {
                "Lexical": " ".join(w["Word"] for w in words),
                "PronunciationAssessment": scores,
                "Words": words,
            }
        ]
    }


def test_scores_are_weighted_by_words_and_issues_keep_global_index() -> None:
    segments = [
        _segment([_word("we", 0, 95), _word("employees", 1, 41, "Mispronunciation")], 80, 70),
        _segment([_word("work", 2, 55), _word("here", 3, 90), _word("today", 4, 90)], 90, None),
    ]
    verbatim = _verbatim(segments)
    pa = _pronunciation(segments)
    assert verbatim.lexical == "we employees work here today"
    assert pa is not None
    assert pa.pron_score == 86.0  # (80*2 + 90*3) / 5
    assert pa.prosody == 70.0  # solo el segmento que la trae
    assert [(i.word, i.error_type, i.word_index) for i in pa.issues] == [
        ("employees", "Mispronunciation", 1),
        ("work", "LowAccuracy", 2),
    ]
    assert pa.issues[0].weak_phonemes == ["m"]
    assert verbatim.words[pa.issues[1].word_index or 0].text == "work"


def test_no_assessment_in_response() -> None:
    assert _pronunciation([{"NBest": [{"Lexical": "hi", "Words": []}]}]) is None


def test_failover_moves_to_the_next_resource_and_remembers() -> None:
    from speak2mytrainer.adapters.outbound.azure_speech import SpeechResource, _Failover
    from speak2mytrainer.domain.errors import ServiceQuotaError

    f0 = SpeechResource("/x/spch-f0", "eastus2")
    s0 = SpeechResource("/x/spch-s0", "eastus2", paid=True)
    calls: list[str] = []

    def call(resource: SpeechResource) -> str:
        calls.append(resource.resource_id)
        if resource is f0:
            raise ServiceQuotaError("F0 agotado")
        return "ok"

    failover = _Failover([f0, s0])
    # Devuelve también quién respondió: el S0 se cobra en el costo estimado.
    assert failover.run(call) == ("ok", s0)
    assert failover.run(call)[1].paid
    # La segunda solicitud ya no toca F0 mientras dura la pausa.
    assert calls == ["/x/spch-f0", "/x/spch-s0", "/x/spch-s0"]


def test_failover_raises_when_every_resource_rejects() -> None:
    from speak2mytrainer.adapters.outbound.azure_speech import SpeechResource, _Failover
    from speak2mytrainer.domain.errors import ServiceQuotaError

    def call(resource: SpeechResource) -> str:
        raise ServiceQuotaError("sin cuota")

    with pytest.raises(ServiceQuotaError):
        _Failover([SpeechResource("/a", "r"), SpeechResource("/b", "r")]).run(call)
