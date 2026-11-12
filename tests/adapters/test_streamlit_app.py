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


def _render_done_attempt() -> None:
    from pathlib import Path as _Path
    from tempfile import mkdtemp

    from speak2mytrainer.adapters.inbound.streamlit_app import WebContext
    from speak2mytrainer.adapters.inbound.streamlit_app.result import render_attempt
    from speak2mytrainer.adapters.outbound import fakes
    from speak2mytrainer.application.use_cases.practices import create_practice
    from speak2mytrainer.bootstrap import Environment, Settings, build_container
    from speak2mytrainer.domain.models import (
        Filler,
        FillerType,
        GrammarIssue,
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
    )
    container = build_container(Settings(env=Environment.CI, local_data_dir=_Path(mkdtemp())))
    container = container.__class__(
        **{**container.__dict__, "analyzer": fakes.FakeTextAnalyzer(analysis)}
    )
    container.users.save(UserProfile(id="ana@x.com", name="Ana"))
    practice = create_practice(container.practices, "ana@x.com", "Entrevista")
    attempt = container.submit_attempt("ana@x.com", practice.id, b"RIFF", "a.wav")
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
        "Versión mejorada",
        "Para tu próximo intento",
    ]
    assert [m.label for m in at.metric] == [
        "Duración",
        "Palabras/min",
        "Muletillas/min",
        "Reinicios",
    ]
    markdown = " ".join(m.value for m in at.markdown)
    assert "**like**" in markdown
    assert "~~we build~~ → **we built**" in markdown
    assert at.info[0].value == "The project was huge and we built it fast."
