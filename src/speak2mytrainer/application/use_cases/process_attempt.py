"""Pipeline del job: audio → transcripciones → disfluencias → LLM → métricas → done."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePath

from speak2mytrainer.application.ports import (
    AnalysisRequest,
    AttemptJob,
    AudioConverter,
    AudioStorage,
    PracticeRepository,
    SpeechRecognizer,
    TextAnalyzer,
    Transcriber,
    UserDirectory,
)
from speak2mytrainer.domain.disfluency import combine_fillers, disfluency_candidates
from speak2mytrainer.domain.errors import DomainError
from speak2mytrainer.domain.metrics import build_metrics
from speak2mytrainer.domain.models import (
    Attempt,
    AttemptStatus,
    ModelInfo,
    can_transition,
)


@dataclass(frozen=True)
class ProcessAttempt:
    practices: PracticeRepository
    users: UserDirectory
    audio: AudioStorage
    converter: AudioConverter
    transcriber: Transcriber
    recognizer: SpeechRecognizer
    analyzer: TextAnalyzer

    def __call__(self, job: AttemptJob, *, final: bool) -> Attempt | None:
        """Procesa un intento. Si falla, lo marca `failed` y relanza la excepción.

        `final` indica que no habrá otro reintento: entonces se devuelve la cuota reservada.
        Devuelve None si el intento ya no existe (el usuario lo borró mientras esperaba).
        """
        attempt = self.practices.get_attempt(job.user_id, job.attempt_id)
        if attempt is None or attempt.status is AttemptStatus.DONE:
            return attempt
        if attempt.status not in (AttemptStatus.QUEUED, AttemptStatus.FAILED):
            # Un job anterior murió a mitad del proceso: se empieza de nuevo.
            attempt.advance(AttemptStatus.FAILED, error="Procesamiento interrumpido.")
        if attempt.status is AttemptStatus.FAILED:
            attempt.advance(AttemptStatus.QUEUED)
        try:
            self._run(attempt)
        except Exception as exc:
            self._fail(attempt, exc, final=final)
            raise
        return attempt

    def abandon(self, job: AttemptJob, reason: str) -> None:
        """Marca el intento `failed` sin procesarlo (p. ej., el job murió en cada intento)."""
        attempt = self.practices.get_attempt(job.user_id, job.attempt_id)
        if attempt is not None:
            self._fail(attempt, DomainError(reason), final=True)

    def _save(self, attempt: Attempt, status: AttemptStatus) -> None:
        attempt.advance(status)
        self.practices.update_attempt(attempt)

    def _run(self, attempt: Attempt) -> None:
        practice = self.practices.get_practice(attempt.user_id, attempt.practice_id)
        user = self.users.get(attempt.user_id)
        language = practice.practice_language if practice else "en"

        self._save(attempt, AttemptStatus.TRANSCRIBING)
        data = self.audio.read(attempt.audio_blob)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            self.converter.to_wav16k(data, PurePath(attempt.audio_blob).suffix, wav)
            # Las dos transcripciones son independientes: en paralelo, Speech marca el ritmo.
            with ThreadPoolExecutor(max_workers=2) as pool:
                transcript_future = pool.submit(self.transcriber.transcribe, wav, language)
                recognition_future = pool.submit(self.recognizer.recognize, wav, language)
                transcript = transcript_future.result()
                verbatim = recognition_future.result().verbatim

        attempt.transcript = transcript.text
        attempt.verbatim_transcript = verbatim.lexical
        self._save(attempt, AttemptStatus.ANALYZING)

        analysis = self.analyzer.analyze(
            AnalysisRequest(
                transcript=transcript.text,
                context=practice.context if practice else None,
                feedback_language=user.feedback_language if user else "es",
                practice_language=language,
                verbatim=verbatim.lexical,
                candidates=tuple(disfluency_candidates(transcript.text, verbatim.lexical)),
            )
        )
        # Las hesitaciones las cuenta Python sobre la forma léxica; del LLM solo se toman
        # reinicios y muletillas léxicas (ADR 0002).
        analysis.fillers = combine_fillers(verbatim.lexical, analysis.fillers)
        attempt.analysis = analysis
        attempt.metrics = build_metrics(
            transcript.text, attempt.duration_sec, analysis.fillers, verbatim
        )
        attempt.models = ModelInfo(
            transcribe=transcript.model,
            llm=self.analyzer.model,
            prompt_version=self.analyzer.prompt_version,
        )
        self._save(attempt, AttemptStatus.DONE)

    def _fail(self, attempt: Attempt, exc: Exception, *, final: bool) -> None:
        if not can_transition(attempt.status, AttemptStatus.FAILED):
            return
        reason = str(exc) if isinstance(exc, DomainError) else "No se pudo analizar el audio."
        suffix = "" if final else " Se reintentará automáticamente."
        attempt.advance(AttemptStatus.FAILED, error=reason + suffix)
        self.practices.update_attempt(attempt)
        if final:
            user = self.users.get(attempt.user_id)
            if user is not None:
                user.quota.refund(attempt.duration_sec)
                self.users.save(user)
