from pathlib import Path

from streamlit.testing.v1 import AppTest

import speak2mytrainer.adapters.inbound.streamlit_app as streamlit_app

PROBE = Path(streamlit_app.__file__).parent / "probe.py"


def test_probe_renders_without_auth_headers() -> None:
    at = AppTest.from_file(str(PROBE)).run()
    assert not at.exception
    assert any("Sin cabeceras de Easy Auth" in i.value for i in at.info)
