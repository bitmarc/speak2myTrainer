"""Pipeline del job: audio → transcripciones → (pronunciación) → disfluencias → LLM → métricas."""

from __future__ import annotations

import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from speak2mytrainer.application.ports import (
    AnalysisRequest,
    AttemptJob,
    Attribute,
    AudioConverter,
    AudioStorage,
    NullTelemetry,
    PracticeRepository,
    SpeechRecognizer,
    Telemetry,
    TextAnalyzer,
    Transcriber,
    UserDirectory,
)
from speak2mytrainer.domain.cost import Prices, Usage, estimate
from speak2mytrainer.domain.disfluency import combine_fillers, disfluency_candidates
from speak2mytrainer.domain.errors import DomainError
from speak2mytrainer.domain.metrics import build_metrics
from speak2mytrainer.domain.models import (
    Attempt,
    AttemptStatus,
    ModelInfo,
    can_transition,
)
from speak2mytrainer.domain.pronunciation import grounded_issues

COMPRESSED_SUFFIX = ".m4a"

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessAttempt:
    practices: PracticeRepository
    users: UserDirectory
    audio: AudioStorage
    converter: AudioConverter
    transcriber: Transcriber
    recognizer: SpeechRecognizer
    analyzer: TextAnalyzer
    prices: Prices = field(default_factory=Prices)
    telemetry: Telemetry = field(default_factory=NullTelemetry)

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
        # Un tramo por intento; sin correo ni texto del usuario (ADR 0005).
        root: dict[str, Attribute] = {
            "attempt.id": attempt.id,
            "attempt.number": attempt.number,
            "attempt.final_delivery": final,
            "attempt.assess_pronunciation": attempt.assess_pronunciation,
            "audio.seconds": attempt.duration_sec,
        }
        with self.telemetry.span("process_attempt", **root):
            try:
                self._run(attempt)
            except Exception as exc:
                self._fail(attempt, exc, final=final)
                raise
            self.telemetry.annotate(
                **{
                    "attempt.status": attempt.status.value,
                    "cost.usd": attempt.cost_estimate_usd or 0,
                }
            )
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
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            with self.telemetry.span("convert"):
                data = self.audio.read(attempt.audio_blob)
                self.converter.to_wav16k(data, PurePath(attempt.audio_blob).suffix, wav)
            # Las dos transcripciones son independientes: en paralelo, Speech marca el ritmo.
            with (
                self.telemetry.span("transcribe"),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                transcript_future = pool.submit(self.transcriber.transcribe, wav, language)
                recognition_future = pool.submit(self.recognizer.recognize, wav, language)
                transcript = transcript_future.result()
                recognition = recognition_future.result()
                self.telemetry.annotate(**{"transcribe.model": transcript.model})
                self.telemetry.annotate(**{"speech.paid": recognition.paid})
            verbatim = recognition.verbatim
            # Segundos de audio que procesó un recurso de pago, sumando las pasadas de Speech.
            speech_paid_sec = attempt.duration_sec if recognition.paid else 0.0
            attempt.transcript = transcript.text
            attempt.verbatim_transcript = verbatim.lexical

            # La evaluación va en una pasada aparte: en la misma pasada Speech pierde ~60% de
            # las hesitaciones (gate del ADR 0003). Va después, porque F0 admite una sola
            # solicitud a la vez.
            pronunciation = None
            if attempt.assess_pronunciation:
                self._save(attempt, AttemptStatus.ASSESSING)
                with self.telemetry.span("assess_pronunciation"):
                    assessed = self.recognizer.recognize(wav, language, assess_pronunciation=True)
                    self.telemetry.annotate(**{"speech.paid": assessed.paid})
                pronunciation = assessed.pronunciation
                if assessed.paid:
                    speech_paid_sec += attempt.duration_sec
                if pronunciation is not None:
                    # Solo palabras que el texto de registro confirma: lo que Speech reconoció
                    # mal no es un error de pronunciación del usuario.
                    pronunciation.issues = grounded_issues(
                        transcript.text,
                        [w.text for w in assessed.verbatim.words],
                        pronunciation.issues,
                    )

        attempt.pronunciation = pronunciation
        self._save(attempt, AttemptStatus.ANALYZING)

        previous = self._previous(attempt)
        request = AnalysisRequest(
            transcript=transcript.text,
            context=practice.context if practice else None,
            feedback_language=user.feedback_language if user else "es",
            practice_language=language,
            verbatim=verbatim.lexical,
            candidates=tuple(disfluency_candidates(transcript.text, verbatim.lexical)),
            previous_transcript=previous.transcript if previous else None,
            previous_analysis=previous.analysis if previous else None,
        )
        with self.telemetry.span(
            "analyze",
            **{
                "llm.model": self.analyzer.model,
                "llm.prompt_version": self.analyzer.prompt_version,
            },
        ):
            result = self.analyzer.analyze(request)
            self.telemetry.annotate(
                **{
                    "llm.input_tokens": result.input_tokens,
                    "llm.output_tokens": result.output_tokens,
                }
            )
        analysis = result.analysis
        # Las hesitaciones las cuenta Python sobre la forma léxica; del LLM solo se toman
        # reinicios y muletillas léxicas (ADR 0002).
        analysis.fillers = combine_fillers(verbatim.lexical, analysis.fillers)
        if analysis.comparison is not None and previous is not None and previous.analysis:
            analysis.comparison.fillers_before = len(previous.analysis.fillers)
            analysis.comparison.fillers_after = len(analysis.fillers)
            analysis.comparison.previous_attempt_number = previous.number
        else:
            analysis.comparison = None
        attempt.analysis = analysis
        attempt.metrics = build_metrics(
            transcript.text, attempt.duration_sec, analysis.fillers, verbatim, pronunciation
        )
        attempt.models = ModelInfo(
            transcribe=transcript.model,
            llm=self.analyzer.model,
            prompt_version=self.analyzer.prompt_version,
        )
        attempt.cost_estimate_usd = estimate(
            Usage(
                transcribe_sec=attempt.duration_sec,
                llm_input_tokens=result.input_tokens,
                llm_output_tokens=result.output_tokens,
                speech_paid_sec=speech_paid_sec,
            ),
            self.prices,
        )
        self._save(attempt, AttemptStatus.DONE)
        self._compress(attempt, data)

    def _compress(self, attempt: Attempt, data: bytes) -> None:
        """Reemplaza el audio original por AAC (~6 veces menos que el WAV del navegador).

        Es de mejor esfuerzo: el análisis ya terminó, así que si falla se conserva el original.
        Se guarda primero el nuevo y se borra el viejo al final, para no perder nada.
        """
        original = attempt.audio_blob
        source = PurePath(original)
        if source.suffix.lower() == COMPRESSED_SUFFIX:
            return  # las notas de voz del iPhone ya vienen en AAC
        target = source.with_suffix(COMPRESSED_SUFFIX).as_posix()
        saved = False
        try:
            with self.telemetry.span("compress_audio", **{"audio.original_bytes": len(data)}):
                compressed = self.converter.to_m4a(data, source.suffix)
                self.audio.save(target, compressed, "audio/mp4")
                attempt.audio_blob = target
                self.practices.update_attempt(attempt)
                saved = True
                self.audio.delete(original)
                self.telemetry.annotate(**{"audio.compressed_bytes": len(compressed)})
        except Exception:
            if not saved:
                attempt.audio_blob = original
            _log.warning("No se pudo comprimir el audio del intento %s", attempt.id, exc_info=True)

    def _previous(self, attempt: Attempt) -> Attempt | None:
        """El último intento analizado de la misma práctica antes de este (RF-15)."""
        done = [
            a
            for a in self.practices.list_attempts(attempt.user_id, attempt.practice_id)
            if a.status is AttemptStatus.DONE and a.number < attempt.number and a.analysis
        ]
        return max(done, key=lambda a: a.number, default=None)

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
