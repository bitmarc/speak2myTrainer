from datetime import timedelta
from pathlib import Path

import pytest

from speak2mytrainer.adapters.outbound import fakes
from speak2mytrainer.application.ports import AttemptJob, Transcript
from speak2mytrainer.application.use_cases import access, practices
from speak2mytrainer.application.use_cases.process_attempt import ProcessAttempt
from speak2mytrainer.application.use_cases.submit_attempt import SubmitAttempt
from speak2mytrainer.domain.errors import (
    AudioDurationError,
    NotAllowedError,
    NotFoundError,
    QuotaExceededError,
    UnsupportedAudioError,
)
from speak2mytrainer.domain.models import (
    AttemptStatus,
    Filler,
    FillerType,
    Quota,
    Role,
    TextAnalysis,
    UserProfile,
)

ADMIN = "admin@x.com"
USER = "ana@x.com"


class World:
    """Todos los fakes conectados, como los arma `bootstrap` en local."""

    def __init__(self, tmp_path: Path, duration: float = 60.0) -> None:
        self.users = fakes.InMemoryUserDirectory(
            [UserProfile(id=USER, name="Ana", quota=Quota(minutes_per_month=5))]
        )
        self.practices = fakes.InMemoryPracticeRepository()
        self.audio = fakes.LocalFolderAudioStorage(tmp_path)
        self.queue = fakes.InMemoryJobQueue()
        self.converter = fakes.FakeAudioConverter(duration=duration)
        self.transcriber = fakes.FakeTranscriber("Well, I once worked on a project.")
        self.recognizer = fakes.FakeSpeechRecognizer("well um i once worked on on a project")
        self.analyzer = fakes.FakeTextAnalyzer(
            TextAnalysis(
                fillers=[
                    Filler(quote="well um i", token="um", type=FillerType.HESITATION),
                    Filler(quote="worked on [on] a", token="on", type=FillerType.RESTART),
                ],
                improved_version="Well, I once worked on a project.",
                next_steps=["a", "b", "c"],
            )
        )
        self.submit = SubmitAttempt(
            self.practices, self.users, self.audio, self.queue, self.converter
        )
        self.process = ProcessAttempt(
            self.practices,
            self.users,
            self.audio,
            self.converter,
            self.transcriber,
            self.recognizer,
            self.analyzer,
        )

    def used_minutes(self) -> float:
        user = self.users.get(USER)
        assert user is not None
        return user.quota.used_this_month


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


# --- acceso y admin ---------------------------------------------------------------------


def test_admin_is_created_on_first_login() -> None:
    users = fakes.InMemoryUserDirectory()
    user = access.resolve_user(users, " Admin@X.com ", "Marco", admin_email=ADMIN)
    assert user.id == ADMIN
    assert user.role is Role.ADMIN
    assert users.get(ADMIN) is not None


def test_unknown_or_revoked_email_is_rejected() -> None:
    users = fakes.InMemoryUserDirectory([UserProfile(id=USER, name="Ana", allowed=False)])
    with pytest.raises(NotAllowedError):
        access.resolve_user(users, "intruso@x.com", None, admin_email=ADMIN)
    with pytest.raises(NotAllowedError):
        access.resolve_user(users, USER, None, admin_email=ADMIN)


def test_admin_manages_whitelist_and_quota() -> None:
    users = fakes.InMemoryUserDirectory()
    admin = access.resolve_user(users, ADMIN, "Marco", admin_email=ADMIN)

    access.allow_user(users, admin, "Amigo@X.com", minutes_per_month=30)
    assert access.resolve_user(users, "amigo@x.com", None, ADMIN).quota.minutes_per_month == 30

    access.set_quota(users, admin, "amigo@x.com", 90)
    access.revoke_user(users, admin, "amigo@x.com")
    revoked = users.get("amigo@x.com")
    assert revoked is not None
    assert revoked.allowed is False
    assert revoked.quota.minutes_per_month == 90

    with pytest.raises(ValueError):
        access.revoke_user(users, admin, ADMIN)


def test_regular_user_cannot_administer() -> None:
    users = fakes.InMemoryUserDirectory([UserProfile(id=USER, name="Ana")])
    user = access.resolve_user(users, USER, None, ADMIN)
    with pytest.raises(NotAllowedError):
        access.allow_user(users, user, "otro@x.com")


def test_feedback_language_preference() -> None:
    users = fakes.InMemoryUserDirectory([UserProfile(id=USER, name="Ana")])
    assert access.set_feedback_language(users, USER, "en").feedback_language == "en"
    with pytest.raises(ValueError):
        access.set_feedback_language(users, USER, "fr")


# --- prácticas y envío ------------------------------------------------------------------


def test_create_practice_requires_title(world: World) -> None:
    with pytest.raises(ValueError):
        practices.create_practice(world.practices, USER, "   ")
    practice = practices.create_practice(world.practices, USER, " Entrevista ", "  ")
    assert practice.title == "Entrevista"
    assert practice.context is None


def test_submit_saves_audio_reserves_quota_and_enqueues(world: World) -> None:
    practice = practices.create_practice(world.practices, USER, "Entrevista")

    attempt = world.submit(USER, practice.id, b"audio", "nota.M4A")

    assert attempt.number == 1
    assert attempt.status is AttemptStatus.QUEUED
    assert attempt.audio_blob == f"audio/{USER}/{practice.id}/{attempt.id}.m4a"
    assert world.audio.read(attempt.audio_blob) == b"audio"
    assert list(world.queue.jobs) == [AttemptJob(USER, practice.id, attempt.id)]
    assert world.used_minutes() == pytest.approx(1.0)
    stored = world.practices.get_practice(USER, practice.id)
    assert stored is not None
    assert stored.attempt_count == 1


def test_submit_rejects_bad_duration_format_and_quota(tmp_path: Path) -> None:
    short = World(tmp_path, duration=5)
    practice = practices.create_practice(short.practices, USER, "p")
    with pytest.raises(AudioDurationError):
        short.submit(USER, practice.id, b"x", "a.wav")
    with pytest.raises(UnsupportedAudioError):
        short.submit(USER, practice.id, b"x", "a.flac")

    long = World(tmp_path, duration=6 * 60)  # la cuota es de 5 min
    practice = practices.create_practice(long.practices, USER, "p")
    with pytest.raises(QuotaExceededError):
        long.submit(USER, practice.id, b"x", "a.wav")
    assert not long.queue.jobs


def test_submit_to_someone_elses_practice_fails(world: World) -> None:
    practice = practices.create_practice(world.practices, "otro@x.com", "p")
    with pytest.raises(NotFoundError):
        world.submit(USER, practice.id, b"x", "a.wav")


# --- pipeline del job -------------------------------------------------------------------


def _submitted(world: World) -> AttemptJob:
    practice = practices.create_practice(world.practices, USER, "Entrevista", "Tell me about it")
    world.submit(USER, practice.id, b"audio", "a.wav")
    return world.queue.jobs.popleft()


def test_process_runs_full_pipeline(world: World) -> None:
    job = _submitted(world)

    attempt = world.process(job, final=False)

    assert attempt is not None
    assert attempt.status is AttemptStatus.DONE
    assert attempt.transcript == "Well, I once worked on a project."
    assert attempt.verbatim_transcript == "well um i once worked on on a project"
    assert attempt.analysis is not None
    # La hesitación la pone Python desde la forma léxica; el reinicio viene del LLM.
    assert [(f.token, f.type) for f in attempt.analysis.fillers] == [
        ("um", FillerType.HESITATION),
        ("on", FillerType.RESTART),
    ]
    assert attempt.metrics is not None
    assert attempt.metrics.words == 9
    assert attempt.metrics.wpm == pytest.approx(150.0)  # 9 palabras en 3.6 s de habla
    assert attempt.metrics.restarts == 1
    # Sin pedirla no hay pronunciación ni segunda pasada de Speech.
    assert attempt.pronunciation is None
    assert attempt.metrics.pron_score is None
    assert world.recognizer.calls == [False]
    assert attempt.models is not None
    assert attempt.models.prompt_version == "fake"

    request = world.analyzer.requests[0]
    assert request.context == "Tell me about it"
    assert request.verbatim == "well um i once worked on on a project"
    assert request.candidates == ("once worked on [on] a project",)


def test_pronunciation_is_a_second_speech_pass(world: World) -> None:
    from speak2mytrainer.domain.models import PronunciationIssue

    world.recognizer.issues = [
        PronunciationIssue(word="project", score=41, error_type="Mispronunciation", word_index=8),
        PronunciationIssue(word="on", score=30, error_type="Mispronunciation", word_index=6),
    ]
    practice = practices.create_practice(world.practices, USER, "Entrevista")
    world.submit(USER, practice.id, b"audio", "a.wav", assess_pronunciation=True)
    statuses: list[AttemptStatus] = []
    update = world.practices.update_attempt
    world.practices.update_attempt = lambda a: (statuses.append(a.status), update(a))[1]  # type: ignore[method-assign]

    attempt = world.process(world.queue.jobs.popleft(), final=False)

    assert attempt is not None and attempt.pronunciation is not None
    assert world.recognizer.calls == [False, True]
    assert statuses == [
        AttemptStatus.TRANSCRIBING,
        AttemptStatus.ASSESSING,
        AttemptStatus.ANALYZING,
        AttemptStatus.DONE,
    ]
    # El "on" repetido no existe en el texto de registro: se descarta.
    assert [i.word for i in attempt.pronunciation.issues] == ["project"]
    assert attempt.metrics is not None
    assert attempt.metrics.pron_score == attempt.pronunciation.pron_score
    # Las muletillas siguen saliendo de la pasada sin evaluación.
    assert attempt.verbatim_transcript == "well um i once worked on on a project"


def test_second_attempt_is_compared_with_the_previous_one(world: World) -> None:
    from speak2mytrainer.domain.models import Comparison

    # El fake devuelve comparación siempre; en el primer intento se descarta.
    world.analyzer.analysis.comparison = Comparison(fixed=["participated in"])
    first = _submitted(world)
    first_attempt = world.process(first, final=False)
    assert first_attempt is not None and first_attempt.analysis is not None
    assert first_attempt.analysis.comparison is None
    assert world.analyzer.requests[0].previous_transcript is None

    world.submit(USER, first.practice_id, b"audio", "b.wav")
    second = world.process(world.queue.jobs.popleft(), final=False)

    assert second is not None and second.analysis is not None
    request = world.analyzer.requests[1]
    assert request.previous_transcript == "Well, I once worked on a project."
    assert request.previous_analysis == first_attempt.analysis
    comparison = second.analysis.comparison
    assert comparison is not None
    assert comparison.fixed == ["participated in"]
    assert comparison.previous_attempt_number == 1
    # Conteos de Python con las muletillas combinadas (um de Python + "on" repetido).
    assert (comparison.fillers_before, comparison.fillers_after) == (2, 2)


def test_process_is_idempotent_once_done(world: World) -> None:
    job = _submitted(world)
    world.process(job, final=False)
    world.process(job, final=False)
    assert len(world.analyzer.requests) == 1


def test_failure_marks_failed_then_retry_succeeds(world: World) -> None:
    job = _submitted(world)
    good = world.transcriber

    class Broken:
        def transcribe(self, wav_path: Path, language: str) -> Transcript:
            raise ConnectionError("timeout")

    object.__setattr__(world.process, "transcriber", Broken())
    with pytest.raises(ConnectionError):
        world.process(job, final=False)
    failed = world.practices.get_attempt(USER, job.attempt_id)
    assert failed is not None
    assert failed.status is AttemptStatus.FAILED
    assert failed.error is not None
    assert "reintentará" in failed.error
    assert world.used_minutes() == pytest.approx(1.0)  # todavía reservada

    object.__setattr__(world.process, "transcriber", good)
    attempt = world.process(job, final=True)
    assert attempt is not None
    assert attempt.status is AttemptStatus.DONE


def test_final_failure_refunds_quota(world: World) -> None:
    job = _submitted(world)

    class Broken:
        def transcribe(self, wav_path: Path, language: str) -> Transcript:
            raise ConnectionError("timeout")

    object.__setattr__(world.process, "transcriber", Broken())
    with pytest.raises(ConnectionError):
        world.process(job, final=True)
    assert world.used_minutes() == 0.0


def test_interrupted_attempt_is_restarted(world: World) -> None:
    job = _submitted(world)
    attempt = world.practices.get_attempt(USER, job.attempt_id)
    assert attempt is not None
    attempt.advance(AttemptStatus.TRANSCRIBING)  # un job anterior murió aquí
    world.practices.update_attempt(attempt)

    done = world.process(job, final=True)
    assert done is not None
    assert done.status is AttemptStatus.DONE


def test_deleted_attempt_is_skipped(world: World) -> None:
    job = _submitted(world)
    practices.delete_history(world.practices, world.audio, USER)
    assert world.process(job, final=False) is None


# --- borrado ----------------------------------------------------------------------------


def test_delete_practice_and_history_remove_audio(world: World, tmp_path: Path) -> None:
    p1 = practices.create_practice(world.practices, USER, "uno")
    p2 = practices.create_practice(world.practices, USER, "dos")
    a1 = world.submit(USER, p1.id, b"1", "a.wav")
    a2 = world.submit(USER, p2.id, b"2", "a.wav")

    practices.delete_practice(world.practices, world.audio, USER, p1.id)
    assert world.practices.get_attempt(USER, a1.id) is None
    assert not (tmp_path / a1.audio_blob).exists()
    assert (tmp_path / a2.audio_blob).exists()

    world.audio.save(f"tts/{USER}/{a2.id}.mp3", b"tts", "audio/mpeg")
    practices.delete_history(world.practices, world.audio, USER)
    assert world.practices.list_practices(USER) == []
    assert not [f for f in tmp_path.rglob("*") if f.is_file()]
    assert world.users.get(USER) is not None  # el perfil y la cuota se conservan


def test_signed_url_is_local_file_uri(world: World) -> None:
    world.audio.save("audio/x.wav", b"1", "audio/wav")
    assert world.audio.signed_url("audio/x.wav", timedelta(minutes=5)).startswith("file:")


def test_configured_admin_keeps_admin_role() -> None:
    users = fakes.InMemoryUserDirectory([UserProfile(id=ADMIN, name="Marco", allowed=False)])
    user = access.resolve_user(users, ADMIN, None, admin_email=ADMIN)
    assert (user.role, user.allowed) == (Role.ADMIN, True)


def test_improved_audio_is_generated_once_per_voice(world: World, tmp_path: Path) -> None:
    from speak2mytrainer.domain.models import VoiceGender

    synthesizer = fakes.FakeSpeechSynthesizer()
    attempt = world.process(_submitted(world), final=False)
    assert attempt is not None
    user = world.users.get(USER)
    assert user is not None

    def listen() -> str:
        return practices.improved_audio(world.practices, world.audio, synthesizer, user, attempt.id)

    path = listen()
    assert path == f"tts/{USER}/{attempt.practice_id}/{attempt.id}-female.mp3"
    assert world.audio.read(path) == b"mp3:female:Well, I once worked on a project."
    assert listen() == path
    assert len(synthesizer.calls) == 1  # la segunda vez sale de la caché

    user = access.set_tts_voice(world.users, USER, VoiceGender.MALE)
    assert listen().endswith("-male.mp3")
    assert [voice for _, _, voice in synthesizer.calls] == ["female", "male"]

    # Borrar la práctica también borra su TTS.
    practices.delete_practice(world.practices, world.audio, USER, attempt.practice_id)
    assert not [f for f in tmp_path.rglob("*.mp3")]


def test_cost_estimate_counts_only_paid_speech(world: World) -> None:
    # Audio de 60 s: transcripción 0.003 + LLM (5k + 2.5k tokens) 0.006; Speech en F0 gratis.
    attempt = world.process(_submitted(world), final=False)
    assert attempt is not None
    assert attempt.cost_estimate_usd == pytest.approx(0.009)

    # Si respondió el S0, cada pasada cobra 1 USD/h: con pronunciación son dos.
    world.recognizer.paid = True
    job = world.submit(USER, attempt.practice_id, b"wav", "a.wav", assess_pronunciation=True)
    paid = world.process(AttemptJob(USER, attempt.practice_id, job.id), final=False)
    assert paid is not None
    assert paid.cost_estimate_usd == pytest.approx(0.009 + 2 * 60 / 3600, abs=1e-6)


def test_process_traces_each_step_without_personal_data(tmp_path: Path) -> None:
    world = World(tmp_path)
    telemetry = fakes.RecordingTelemetry()
    process = ProcessAttempt(
        world.practices,
        world.users,
        world.audio,
        world.converter,
        world.transcriber,
        world.recognizer,
        world.analyzer,
        telemetry=telemetry,
    )
    practice = practices.create_practice(world.practices, USER, "Entrevista", None)
    world.submit(USER, practice.id, b"audio", "a.wav", assess_pronunciation=True)
    attempt = process(world.queue.jobs.popleft(), final=False)
    assert attempt is not None

    names = [name for name, _ in telemetry.spans]
    assert names == ["process_attempt", "convert", "transcribe", "assess_pronunciation", "analyze"]
    root = telemetry.spans[0][1]
    assert root["attempt.id"] == attempt.id
    assert root["attempt.status"] == "done"
    assert root["cost.usd"] == attempt.cost_estimate_usd
    assert telemetry.spans[-1][1]["llm.input_tokens"] == 5_000
    # Ningún atributo lleva el correo ni el texto del usuario.
    values = [str(v) for _, attrs in telemetry.spans for v in attrs.values()]
    assert not any(USER in v or "worked on" in v for v in values)


def test_improved_audio_adds_the_tts_cost(world: World) -> None:
    attempt = world.process(_submitted(world), final=False)
    assert attempt is not None
    user = world.users.get(USER)
    assert user is not None
    synthesizer = fakes.FakeSpeechSynthesizer(paid=True)
    practices.improved_audio(world.practices, world.audio, synthesizer, user, attempt.id)
    saved = world.practices.get_attempt(USER, attempt.id)
    assert saved is not None
    chars = len("Well, I once worked on a project.")
    assert saved.cost_estimate_usd == pytest.approx(0.009 + chars * 15 / 1_000_000, abs=1e-6)


def test_improved_audio_needs_a_finished_attempt(world: World) -> None:
    job = _submitted(world)
    user = world.users.get(USER)
    assert user is not None
    with pytest.raises(NotFoundError):
        practices.improved_audio(
            world.practices, world.audio, fakes.FakeSpeechSynthesizer(), user, job.attempt_id
        )
