"""Adaptadores contra Azure y ffmpeg reales. No corren en CI.

Requieren `az login`, el `.env` de `scripts/deploy-infra.ps1`, ffmpeg y un audio en
`spikes/audio/`. Uso:  uv run pytest -m integration
"""

from __future__ import annotations

import itertools
import subprocess
import urllib.request
import uuid
import wave
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from speak2mytrainer.application.ports import AttemptJob
from speak2mytrainer.bootstrap import AzureSettings
from speak2mytrainer.domain.models import Attempt, Practice, UserProfile

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
AUDIOS = sorted((ROOT / "spikes" / "audio").glob("*.m4a"))


@pytest.fixture(scope="module")
def azure() -> AzureSettings:
    try:
        return AzureSettings(_env_file=ROOT / ".env")  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"Sin configuración de Azure: {exc}")


@pytest.fixture(scope="module")
def credential():  # type: ignore[no-untyped-def]
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


@pytest.fixture(scope="module")
def sample_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Los primeros 25 s de un audio real, en WAV 16 kHz mono (pocos minutos de Speech)."""
    if not AUDIOS:
        pytest.skip("No hay audios en spikes/audio/")
    from speak2mytrainer.adapters.outbound.ffmpeg import FfmpegAudioConverter, _tool

    converter = FfmpegAudioConverter()
    full = tmp_path_factory.mktemp("audio") / "full.wav"
    converter.to_wav16k(AUDIOS[0].read_bytes(), AUDIOS[0].suffix, full)
    clip = full.with_name("clip.wav")
    subprocess.run(
        [_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", str(full), "-t", "25", str(clip)],
        check=True,
    )
    return clip


def test_ffmpeg_duration_and_conversion(sample_wav: Path) -> None:
    from speak2mytrainer.adapters.outbound.ffmpeg import FfmpegAudioConverter

    duration = FfmpegAudioConverter().duration_sec(AUDIOS[0].read_bytes(), AUDIOS[0].suffix)
    assert duration > 10
    with wave.open(str(sample_wav)) as w:
        assert (w.getframerate(), w.getnchannels()) == (16000, 1)


def test_transcriber(azure: AzureSettings, credential, sample_wav: Path) -> None:  # type: ignore[no-untyped-def]
    from azure.identity import get_bearer_token_provider

    from speak2mytrainer.adapters.outbound.azure_openai.transcriber import AzureOpenAITranscriber

    transcriber = AzureOpenAITranscriber(
        azure.azure_openai_endpoint,
        azure.azure_openai_transcribe_deployment,
        get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default"),
    )
    transcript = transcriber.transcribe(sample_wav, "en")
    assert len(transcript.text.split()) > 20


def _speech(azure: AzureSettings, fallback: bool = False):  # type: ignore[no-untyped-def]
    from speak2mytrainer.adapters.outbound.azure_speech import SpeechResource

    if not fallback:
        return [SpeechResource(azure.azure_speech_resource_id, azure.azure_speech_region)]
    if not azure.azure_speech_fallback_resource_id:
        pytest.skip("Sin recurso S0 de respaldo en .env")
    region = azure.azure_speech_fallback_region or azure.azure_speech_region
    return [SpeechResource(azure.azure_speech_fallback_resource_id, region)]


@pytest.mark.parametrize("fallback", [False, True], ids=["f0", "s0"])
def test_speech_assesses_pronunciation(  # type: ignore[no-untyped-def]
    azure: AzureSettings, credential, sample_wav: Path, fallback: bool
) -> None:
    from speak2mytrainer.adapters.outbound.azure_speech import AzureSpeechRecognizer

    recognizer = AzureSpeechRecognizer(credential, _speech(azure, fallback))
    result = recognizer.recognize(sample_wav, "en", assess_pronunciation=True)
    pa = result.pronunciation
    assert pa is not None
    assert 0 < pa.pron_score <= 100
    assert pa.prosody is not None  # en-US
    assert all(0 <= (i.word_index or 0) < len(result.verbatim.words) for i in pa.issues)


@pytest.mark.parametrize("voice", ["female", "male"])
def test_speech_synthesizer_returns_mp3(  # type: ignore[no-untyped-def]
    azure: AzureSettings, credential, voice: str
) -> None:
    from speak2mytrainer.adapters.outbound.azure_speech import AzureSpeechSynthesizer
    from speak2mytrainer.domain.models import VoiceGender

    synthesizer = AzureSpeechSynthesizer(
        credential,
        _speech(azure),
        {
            VoiceGender.FEMALE: azure.azure_tts_voice_female,
            VoiceGender.MALE: azure.azure_tts_voice_male,
        },
    )
    data = synthesizer.synthesize("We built it in two weeks.", "en", VoiceGender(voice))
    assert len(data) > 2000
    assert data[:3] == b"ID3" or data[0] == 0xFF  # cabecera ID3 o marco MPEG


def test_speech_recognizer_returns_timed_words(  # type: ignore[no-untyped-def]
    azure: AzureSettings, credential, sample_wav: Path
) -> None:
    from speak2mytrainer.adapters.outbound.azure_speech import (
        AzureSpeechRecognizer,
        SpeechResource,
    )

    resource = SpeechResource(azure.azure_speech_resource_id, azure.azure_speech_region)
    result = AzureSpeechRecognizer(credential, [resource]).recognize(sample_wav, "en")
    words = result.verbatim.words
    assert len(words) > 20
    assert result.verbatim.lexical.split()[0] == words[0].text
    assert all(a.start_sec <= b.start_sec for a, b in itertools.pairwise(words))
    assert 0 < words[-1].end_sec <= 26


@pytest.fixture
def user_id() -> str:
    return f"it-{uuid.uuid4().hex[:8]}@test.local"


@pytest.fixture
def cosmos(azure: AzureSettings, credential, user_id: str) -> Iterator[object]:  # type: ignore[no-untyped-def]
    from speak2mytrainer.adapters.outbound.cosmos import CosmosStore

    store = CosmosStore(azure.azure_cosmos_endpoint, azure.azure_cosmos_database, credential)
    yield store
    from speak2mytrainer.adapters.outbound.cosmos import CosmosPracticeRepository

    CosmosPracticeRepository(store).delete_all(user_id)
    for item in store.users.query_items(
        "SELECT c.id FROM c WHERE c.userId = @u",
        parameters=[{"name": "@u", "value": user_id}],
        partition_key=user_id,
    ):
        store.users.delete_item(item["id"], partition_key=user_id)


def test_cosmos_repository_and_directory(cosmos, user_id: str) -> None:  # type: ignore[no-untyped-def]
    from speak2mytrainer.adapters.outbound.cosmos import (
        CosmosPracticeRepository,
        CosmosUserDirectory,
    )

    users = CosmosUserDirectory(cosmos)
    profile = UserProfile(id=user_id, name="Prueba")
    users.save(profile)
    assert users.get(user_id) == profile
    assert user_id in {u.id for u in users.list_users()}

    repo = CosmosPracticeRepository(cosmos)
    practice = Practice(id=uuid.uuid4().hex, user_id=user_id, title="Prueba")
    repo.add_practice(practice)
    attempt = Attempt(
        id=uuid.uuid4().hex,
        user_id=user_id,
        practice_id=practice.id,
        number=1,
        audio_blob="audio/x.wav",
        duration_sec=12.0,
    )
    repo.add_attempt(attempt)
    attempt.transcript = "hola"
    repo.update_attempt(attempt)

    assert repo.get_practice(user_id, practice.id) == practice
    assert repo.get_practice("otro@test.local", practice.id) is None
    assert [p.id for p in repo.list_practices(user_id)] == [practice.id]
    assert repo.list_attempts(user_id, practice.id) == [attempt]

    repo.delete_practice(user_id, practice.id)
    assert repo.get_attempt(user_id, attempt.id) is None
    assert repo.list_practices(user_id) == []


def test_blob_storage_with_user_delegation_sas(  # type: ignore[no-untyped-def]
    azure: AzureSettings, credential, user_id: str
) -> None:
    from speak2mytrainer.adapters.outbound.blob import BlobAudioStorage

    storage = BlobAudioStorage(azure.azure_storage_blob_endpoint, credential)
    path = f"audio/{user_id}/p1/a1.wav"
    storage.save(path, b"RIFF-test", "audio/wav")
    try:
        assert storage.read(path) == b"RIFF-test"
        url = storage.signed_url(path, timedelta(minutes=5))
        with urllib.request.urlopen(url, timeout=30) as response:
            assert response.read() == b"RIFF-test"
    finally:
        storage.delete_prefix(f"audio/{user_id}/")
    with pytest.raises(Exception):  # noqa: B017
        storage.read(path)


def test_storage_queue_roundtrip(azure: AzureSettings, credential) -> None:  # type: ignore[no-untyped-def]
    from speak2mytrainer.adapters.outbound.storage_queue import (
        StorageQueueJobQueue,
        decode_job,
        queue_client,
    )

    # Cola temporal: la cola real dispara el job en Azure.
    client = queue_client(
        azure.azure_storage_queue_endpoint, credential, f"it-{uuid.uuid4().hex[:8]}"
    )
    client.create_queue()
    try:
        job = AttemptJob(user_id="u@test.local", practice_id="p", attempt_id="a")
        StorageQueueJobQueue(client).enqueue(job)
        message = next(iter(client.receive_messages(visibility_timeout=30)))
        assert decode_job(message.content) == job
    finally:
        client.delete_queue()
