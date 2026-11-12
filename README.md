# speak2myTrainer

Entrenador de voz para practicar inglés hablado. Grabas o subes una respuesta de 10 s a 10 min y recibes métricas de fluidez, muletillas con cita, errores gramaticales, pronunciación y una versión mejorada que puedes escuchar antes de volver a intentar.

> Estado: **Fase 0 · Spike y fundaciones**. Ver el [PRD](docs/PRD/) y las [decisiones de arquitectura](docs/adr/).

## Stack

- 100% Python 3.12: Streamlit como web y un Container Apps Job para el análisis.
- Azure: Container Apps (escala a cero), Storage (Blob y Queue), Cosmos DB en nivel gratuito, Azure OpenAI (`gpt-4o-mini-transcribe`, `gpt-4.1-mini`) y Azure AI Speech.
- Infraestructura como código en Bicep (`infra/`) y CI/CD con GitHub Actions.
- Presupuesto: 15 USD/mes como máximo.

## Arquitectura

Hexagonal (puertos y adaptadores), ver [ADR 0001](docs/adr/0001-arquitectura-hexagonal.md):

```
src/speak2mytrainer/
  domain/        entidades y reglas puras (métricas, estados, cuota)
  application/   casos de uso + ports.py (Protocols)
  adapters/      inbound (streamlit_app, worker_job) · outbound (Azure, fakes)
  bootstrap.py   raíz de composición
```

La regla de dependencias se verifica en CI con `import-linter`.

## Desarrollo

```bash
uv sync --all-extras    # crea .venv con Python 3.12, deps de desarrollo y extras azure + web
uv run pytest           # tests (usan fakes, sin Azure)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports     # regla de capas hexagonales
```

Infraestructura: ver [`infra/README.md`](infra/README.md).
