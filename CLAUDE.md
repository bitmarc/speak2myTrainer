# speak2myTrainer

App web (Streamlit + Container Apps Job) para practicar inglés hablado. Fuente de verdad: `docs/PRD/` y `docs/adr/`.

## Comandos

```bash
uv sync --all-extras                          # Python 3.12, deps de dev y extras azure + web
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports                           # regla de capas hexagonales
az bicep build --file infra/main.bicep        # validar infra
./scripts/deploy-infra.ps1 [-WhatIf]          # desplegar infra y generar .env
```

## Reglas de arquitectura (ADR 0001)

- `domain/` no importa nada del proyecto; `application/` solo importa `domain`; los adaptadores importan hacia dentro; solo `bootstrap.py` conoce los adaptadores concretos.
- Prohibido importar `azure`, `openai` o `streamlit` desde `domain/` o `application/` (import-linter lo verifica).
- Los puertos son `typing.Protocol` en `application/ports.py` y cada uno tiene su fake en `adapters/outbound/fakes/`.
- Las métricas numéricas se calculan en Python (`domain/metrics.py`); el LLM solo clasifica, explica y reescribe.
- Los prompts viven en `adapters/outbound/azure_openai/prompts/` con `PROMPT_VERSION`.
- Sin llaves: todo usa `DefaultAzureCredential` (local: `az login`; Azure: identidad administrada).
- Los nombres de los deployments de modelos son configuración, nunca constantes en el código.

## Convenciones

- Código y comentarios en español; identificadores en inglés.
- `spikes/` es código desechable de la Fase 0, fuera del paquete; los audios en `spikes/audio/` no se versionan.
