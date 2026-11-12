# Spikes de la Fase 0

Código desechable para tomar decisiones con datos antes de escribir la app. Requiere la infra desplegada (`scripts/deploy-infra.ps1`, que genera `.env`) y ffmpeg.

## 1. Graba los audios

Pon 5 grabaciones reales en `spikes/audio/` (no se versionan). Puedes usar cualquier formato: .m4a, .mp3, .wav, .ogg, .webm o .aac. Sugerencia:

| # | Contenido | Duración |
| --- | --- | --- |
| 1 | El ejemplo del PRD (*Tell me about a challenging project…*) | 1–2 min |
| 2 | Otra respuesta de entrevista técnica | 3–5 min (sirve para el spike de pronunciación) |
| 3 | Opinión libre con muchas muletillas léxicas (*like*, *you know*) | 1–2 min |
| 4 | Habla lenta y cuidada | ~1 min |
| 5 | Grabado desde el iPhone (.m4a) en un lugar con ruido | ~1 min |

## 2. Transcripción verbatim

```bash
uv sync --extra azure
uv run python spikes/spike_transcribe.py
```

Resultado en `spikes/results/transcribe_report.md`. Compara a mano cuántas muletillas oyes contra cuántas conserva cada motor.

## 3. Pronunciación

```bash
uv run python spikes/spike_pronunciation.py spikes/audio/<audio_de_3_a_5_min>.m4a
```

Compara el modo no guionizado con el modo guionizado: puntajes, palabras marcadas y tiempo.

## Decisiones que salen de aquí

- ADR 0002: motor de transcripción y prompt.
- ADR 0003: modo de evaluación de pronunciación.
