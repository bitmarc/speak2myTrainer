# ADR 0001 — Arquitectura hexagonal (puertos y adaptadores)

- **Estado:** Aceptada
- **Fecha:** 2026-11-12
- **Autor:** Marco
- **Relacionado:** PRD — speak2myTrainer (sección "Arquitectura propuesta")

## Contexto

speak2myTrainer analiza grabaciones de voz para practicar inglés: transcribe, evalúa pronunciación, calcula métricas y pide a un LLM muletillas, errores gramaticales, una versión mejorada y la comparación con el intento anterior.

Varias fuerzas empujan a aislar la lógica de la infraestructura:

1. **Los modelos de IA cambian rápido.** En Azure, `whisper@001` se retira el 15-dic-2026, `gpt-4.1-mini` el 14-abr-2027 y `gpt-4o-mini-transcribe` (2025-12-15) el 15-jun-2027. El proyecto tendrá que cambiar de modelo al menos una vez en su primer año.
2. **Hay dos puntos de entrada con la misma lógica:** la web (Streamlit), que crea prácticas y encola intentos, y el Container Apps Job, que procesa la cola. Ambos deben usar los mismos casos de uso.
3. **La interfaz no está decidida del todo.** Streamlit es la opción del MVP, pero NiceGUI o una API con FastAPI siguen siendo alternativas.
4. **El presupuesto es de 15 USD/mes.** Los tests y el set de evaluación no pueden depender de llamar a Azure en cada ejecución de CI.
5. **Es un proyecto de portafolio:** la estructura del código debe comunicar decisiones de diseño con claridad.

## Decisión

Adoptar una **arquitectura hexagonal pragmática**:

- **`domain/`**: entidades y reglas puras (`Practice`, `Attempt`, `Metrics`, `Filler`, `GrammarIssue`, cálculo de WPM y muletillas por minuto). Sin E/S y sin dependencias del proyecto.
- **`application/`**: casos de uso (`SubmitAttempt`, `AnalyzeAttempt`, `CompareAttempts`, `GetHistory`, `DeleteHistory`) y los **puertos** en `ports.py`, definidos como `typing.Protocol`.
- **`adapters/inbound/`**: `streamlit_app/` y `worker_job/`. Traducen la entrada (HTTP o mensaje de cola) a llamadas a casos de uso. La identidad de Easy Auth (`X-MS-CLIENT-PRINCIPAL`) se lee aquí y llega al núcleo como un `UserId`.
- **`adapters/outbound/`**: una implementación por servicio de Azure, más `fakes/` para tests.
- **`bootstrap.py`**: la única raíz de composición. Elige qué adaptadores inyectar según el entorno (`local`, `ci`, `azure`).

### Puertos

| Puerto | Responsabilidad | Adaptador Azure | Adaptador de prueba |
| --- | --- | --- | --- |
| `Transcriber` | Audio al texto de registro, el que ve el usuario (ADR 0002) | Azure OpenAI `gpt-4o-mini-transcribe` | Transcripción fija |
| `SpeechRecognizer` | Audio a forma léxica con marcas de tiempo; con `assess_pronunciation`, una pasada aparte con los puntajes de pronunciación (ADR 0002 y 0003) | Azure AI Speech (F0, con failover a S0) | Texto léxico fijo y puntajes fijos |
| `AudioConverter` | Duración, conversión a WAV 16 kHz mono y compresión a AAC tras el análisis | ffmpeg / ffprobe | Duración fija |
| `TextAnalyzer` | Transcripción, contexto e intento previo a análisis estructurado, con los tokens usados | Azure OpenAI `gpt-4.1-mini` + Structured Outputs | Respuestas grabadas |
| `SpeechSynthesizer` | Versión mejorada a mp3 con la voz que eligió el usuario | Azure AI Speech TTS (F0, con failover a S0) | Bytes que identifican voz y texto |
| `AudioStorage` | Guardar, leer, borrar y firmar URL | Blob Storage + SAS | Carpeta local |
| `PracticeRepository` | Prácticas, intentos y gasto del mes por usuario | Cosmos DB | En memoria |
| `UserDirectory` | Lista blanca, preferencias, cuotas | Cosmos DB | En memoria |
| `JobQueue` | Encolar un intento | Azure Storage Queue | Cola en memoria |
| `Telemetry` | Un tramo por paso del pipeline, con tiempos y costo (ADR 0005) | OpenTelemetry → Application Insights | `NullTelemetry` y `RecordingTelemetry` |

### Regla de dependencias

```
adapters  ──►  application  ──►  domain
bootstrap ──►  adapters (único lugar que conoce implementaciones concretas)
```

Se verifica en CI con **import-linter**:

```toml
[tool.importlinter]
root_package = "speak2mytrainer"

[[tool.importlinter.contracts]]
name = "Capas hexagonales"
type = "layers"
layers = [
  "speak2mytrainer.bootstrap",
  "speak2mytrainer.adapters",
  "speak2mytrainer.application",
  "speak2mytrainer.domain",
]
```

### Estructura

```
src/speak2mytrainer/
  domain/
  application/
    ports.py
    use_cases/
  adapters/
    inbound/
      streamlit_app/
      worker_job/
    outbound/
      azure_openai/
      azure_speech/
      cosmos/
      blob/
      storage_queue/
      fakes/
  bootstrap.py
infra/          # Bicep
evals/          # set de frases ambiguas y runner
docs/adr/
tests/
.github/workflows/
```

### Límites para no sobrediseñar

- Unos **8 puertos**, nombrados por capacidad (`Transcriber`), no por tecnología (`OpenAIClient`).
- **Sin repositorio genérico** por entidad, sin agregados ni eventos de dominio de DDD completo, sin bus de comandos.
- Los modelos de dominio son `dataclasses` o `pydantic.BaseModel`. El esquema JSON del LLM se valida en el adaptador y se traduce a objetos de dominio; el núcleo nunca ve el JSON crudo.
- Los prompts viven junto a su adaptador (`adapters/outbound/azure_openai/prompts/`) con una `PROMPT_VERSION` que se guarda en cada intento.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
| --- | --- |
| **Capas simples** (`ui/`, `services/`, `db/`) | Más rápida al inicio, pero los servicios terminan llamando directo a los SDKs de Azure. Cambiar de modelo o probar sin Azure obliga a hacer mocks frágiles. |
| **Clean Architecture completa** (entidades, casos de uso, presenters, gateways, DTOs por capa) | Demasiadas capas y mapeos para una app de menos de 20 usuarios; ralentiza el MVP sin beneficio adicional frente a la versión pragmática. |
| **Lógica dentro de Streamlit** | El job no podría reutilizarla y migrar de UI implicaría reescribir todo. |

## Consecuencias

**Positivas**

- Cambiar de modelo o de proveedor (transcripción, LLM, TTS) es escribir un adaptador y cambiar `bootstrap.py`.
- Tests de dominio y de casos de uso rápidos y gratuitos con los fakes; el set de evaluación de reglas corre en cada PR.
- La web y el job comparten los mismos casos de uso; una futura API con FastAPI sería otro adaptador de entrada.
- La estructura del repo explica la arquitectura a un revisor de portafolio.

**Negativas**

- Algo más de código inicial: protocolos, fakes y la raíz de composición.
- Hay que vigilar que no se filtren tipos de los SDKs (`azure.*`, `openai.*`) hacia `application/` o `domain/`; import-linter lo detecta.
- Las pruebas de integración con Azure reales siguen siendo necesarias; se ejecutan aparte (manual o nocturnas), no en cada PR.
