from pathlib import Path

from speak2mytrainer.application.ports import AttemptJob
from speak2mytrainer.bootstrap import Environment, Settings, build_container
from speak2mytrainer.domain.models import Practice


def test_local_container_wires_fakes(tmp_path: Path) -> None:
    container = build_container(Settings(env=Environment.CI, local_data_dir=tmp_path))

    container.practices.add_practice(Practice(id="p1", user_id="u@x.com", title="Interview"))
    assert [p.id for p in container.practices.list_practices("u@x.com")] == ["p1"]
    assert container.practices.list_practices("other@x.com") == []

    container.audio.save("audio/u@x.com/p1/a1.wav", b"RIFF", "audio/wav")
    assert container.audio.read("audio/u@x.com/p1/a1.wav") == b"RIFF"
    container.audio.delete_prefix("audio/u@x.com/")
    assert not (tmp_path / "audio/u@x.com/p1/a1.wav").exists()

    container.queue.enqueue(AttemptJob(user_id="u@x.com", practice_id="p1", attempt_id="a1"))
