from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import speak2mytrainer.entrypoints as entrypoints

WEB = str(Path(entrypoints.__file__).parent / "web.py")


@pytest.fixture(autouse=True)
def local_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("S2MT_ENV", "ci")
    monkeypatch.setenv("S2MT_LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S2MT_ADMIN_EMAIL", "admin@x.com")
    monkeypatch.delenv("S2MT_DEV_USER", raising=False)
    st.cache_resource.clear()


def test_admin_sees_history_and_admin_page() -> None:
    at = AppTest.from_file(WEB, default_timeout=30).run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Mis prácticas"]
    assert any("Aún no tienes prácticas" in i.value for i in at.info)


def test_unknown_user_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S2MT_DEV_USER", "intruso@x.com")
    at = AppTest.from_file(WEB, default_timeout=30).run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Acceso restringido"]


def _render_done_attempt(attempts: int = 1) -> None:
    from pathlib import Path as _Path
    from tempfile import mkdtemp

    from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
    from speak2mytrainer.adapters.inbound.streamlit_app.result import render_attempt
    from speak2mytrainer.adapters.outbound import fakes
    from speak2mytrainer.application.use_cases.practices import create_practice
    from speak2mytrainer.bootstrap import Environment, Settings, build_container
    from speak2mytrainer.domain.models import (
        Comparison,
        Filler,
        FillerType,
        GrammarIssue,
        PronunciationIssue,
        Severity,
        TextAnalysis,
        UserProfile,
    )

    analysis = TextAnalysis(
        fillers=[Filler(quote="was, like, huge", token="like", type=FillerType.LEXICAL)],
        grammar=[
            GrammarIssue(quote="we build", fix="we built", why="Pasado.", severity=Severity.ERROR)
        ],
        improved_version="The project was huge and we built it fast.",
        next_steps=["Uno", "Dos", "Tres"],
        comparison=Comparison(fixed=["Usaste el pasado: we built"], regressed=["Más pausas"]),
    )
    container = build_container(Settings(env=Environment.CI, local_data_dir=_Path(mkdtemp())))
    # "rock" no está en el texto de registro: el pipeline la descarta (ADR 0003).
    recognizer = fakes.FakeSpeechRecognizer(
        lexical="well um i once worked on a rock project",
        issues=[
            PronunciationIssue(word="rock", score=30, error_type="Mispronunciation", word_index=7),
            PronunciationIssue(
                word="project",
                score=41,
                error_type="Mispronunciation",
                weak_phonemes=["dʒ"],
                word_index=8,
            ),
        ],
    )
    container = container.__class__(
        **{
            **container.__dict__,
            "analyzer": fakes.FakeTextAnalyzer(analysis),
            "recognizer": recognizer,
        }
    )
    container.users.save(UserProfile(id="ana@x.com", name="Ana"))
    practice = create_practice(container.practices, "ana@x.com", "Entrevista")
    for _ in range(attempts):
        attempt = container.submit_attempt(
            "ana@x.com", practice.id, b"RIFF", "a.wav", assess_pronunciation=True
        )
        job = container.queue.jobs.popleft()  # type: ignore[attr-defined]
        container.process_attempt(job, final=True)
    done = container.practices.get_attempt("ana@x.com", attempt.id)
    render_attempt(WebContext(container), done)  # type: ignore[arg-type]


def test_result_shows_all_blocks() -> None:
    at = AppTest.from_function(_render_done_attempt, default_timeout=30).run()
    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "Muletillas",
        "Gramática",
        "Pronunciación",
        "Versión mejorada",
        "Para tu próximo intento",
    ]
    assert [m.label for m in at.metric] == [
        "Duración",
        "Palabras/min",
        "Muletillas/min",
        "Reinicios",
        "Pronunciación",
        "Precisión",
        "Fluidez",
        "Prosodia",
    ]
    markdown = " ".join(m.value for m in at.markdown)
    assert "**project** · 41/100 · sonidos débiles: /dʒ/" in markdown
    assert "rock" not in markdown
    assert "**like**" in markdown
    assert "~~we build~~ → **we built**" in markdown
    assert at.info[0].value == "The project was huge and we built it fast."


def test_second_attempt_shows_comparison_and_deltas() -> None:
    at = AppTest.from_function(_render_done_attempt, args=(2,), default_timeout=30).run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    assert "Comparado con el intento 1" in subheaders
    assert subheaders.index("Comparado con el intento 1") < subheaders.index(
        "Para tu próximo intento"
    )
    # Mismos fakes en los dos intentos: sin cambios, no se muestran deltas.
    assert all(not m.delta for m in at.metric)
    markdown = " ".join(m.value for m in at.markdown)
    assert "Usaste el pasado: we built" in markdown
    assert "Más pausas" in markdown


def _render_kept_attempt() -> None:
    """Como `_render_done_attempt`, pero el contenedor vive en la sesión entre reruns."""
    from pathlib import Path as _Path
    from tempfile import mkdtemp

    import streamlit as st

    from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
    from speak2mytrainer.adapters.inbound.streamlit_app.result import render_attempt
    from speak2mytrainer.adapters.outbound import fakes
    from speak2mytrainer.application.use_cases.practices import create_practice
    from speak2mytrainer.bootstrap import Environment, Settings, build_container
    from speak2mytrainer.domain.models import TextAnalysis, UserProfile

    if "world" not in st.session_state:
        container = build_container(Settings(env=Environment.CI, local_data_dir=_Path(mkdtemp())))
        container = container.__class__(
            **{
                **container.__dict__,
                "analyzer": fakes.FakeTextAnalyzer(
                    TextAnalysis(improved_version="We built it fast.", next_steps=[])
                ),
            }
        )
        container.users.save(UserProfile(id="ana@x.com", name="Ana"))
        practice = create_practice(container.practices, "ana@x.com", "Entrevista")
        attempt = container.submit_attempt("ana@x.com", practice.id, b"RIFF", "a.wav")
        container.process_attempt(container.queue.jobs.popleft(), final=True)  # type: ignore[attr-defined]
        st.session_state["world"] = (container, practice.id, attempt.id)
    container, practice_id, attempt_id = st.session_state["world"]
    if st.session_state.get("recording"):
        st.session_state[f"new-attempt-{practice_id}"] = True
    render_attempt(WebContext(container), container.practices.get_attempt("ana@x.com", attempt_id))


def test_listen_generates_the_improved_audio_once() -> None:
    at = AppTest.from_function(_render_kept_attempt, default_timeout=30).run()
    assert not at.exception
    assert len(at.get("audio")) == 1  # el audio original, en "Transcripción y audio"
    at.button(key=next(b.key for b in at.button if b.label == "Escuchar")).click().run()
    assert not at.exception
    assert len(at.get("audio")) == 2  # ahora suena el mp3
    # En la siguiente visita sale de la caché, sin botón.
    at.run()
    assert len(at.get("audio")) == 2
    assert not [b for b in at.button if b.label == "Escuchar"]


def test_improved_version_is_blurred_while_recording() -> None:
    at = AppTest.from_function(_render_kept_attempt, default_timeout=30)
    at.session_state["recording"] = True
    at.run()
    assert not at.exception
    assert not at.info  # ya no se muestra en claro
    assert any("filter: blur" in m.value for m in at.markdown)
    assert not [b for b in at.button if b.label == "Escuchar"]

    at.session_state["hide-improved-widget"] = False
    at.run()
    assert [i.value for i in at.info] == ["We built it fast."]


def test_metric_delta_against_previous_attempt() -> None:
    from speak2mytrainer.adapters.inbound.streamlit_app.result import _delta
    from speak2mytrainer.domain.models import Metrics

    before = Metrics(duration_sec=60, words=120, wpm=120, fillers_per_min=4.0, restarts=2)
    assert _delta(3.2, before, "fillers_per_min", 1) == "-0.8"
    assert _delta(2, before, "restarts", 0) is None  # sin cambio, sin delta
    assert _delta(80.0, before, "pron_score", 0) is None  # el anterior no evaluó pronunciación
    assert _delta(130.0, None, "wpm", 0) is None
