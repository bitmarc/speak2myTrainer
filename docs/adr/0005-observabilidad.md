# ADR 0005: Observabilidad con Application Insights y OpenTelemetry

- **Estado:** Aceptada
- **Fecha:** 2026-11-13
- **Autor:** Marco
- **Relacionado:** PRD (Fase 3), ADR 0001, `application/ports.py` (`Telemetry`), `adapters/outbound/app_insights/`, `infra/modules/monitoring.bicep`

## Contexto

Hasta la Fase 2, los contenedores solo escribían logs de consola a Log Analytics. Saber cuánto tardó cada paso de un intento (conversión, transcripción, evaluación, LLM) o cuánto costó obligaba a cruzar líneas de log a mano. El PRD pide trazas por intento con tiempos y costo estimado.

Opciones:

| Opción | A favor | En contra |
| --- | --- | --- |
| **Application Insights con OpenTelemetry** | Vista en cascada por intento, dependencias de Cosmos y Blob automáticas, consultas KQL sobre el mismo workspace | Una dependencia más (`azure-monitor-opentelemetry`) |
| Solo logs estructurados (JSON) en Log Analytics | Sin dependencias nuevas | Sin cascada; los tiempos se reconstruyen a mano |

## Decisión

- **Application Insights basado en el workspace existente**, que conserva su retención de 30 días y su tope diario (~5 GB al mes, dentro de lo gratuito).
- **Sin llaves:** el recurso tiene `DisableLocalAuth`, así que la cadena de conexión no sirve para enviar datos. Cada proceso exporta con `DefaultAzureCredential`, y la identidad de las apps y el desarrollador tienen el rol *Monitoring Metrics Publisher*.
- **Puerto `Telemetry`** (`span`, `annotate`): el caso de uso abre tramos sin importar OpenTelemetry. `NullTelemetry` es el valor por defecto y `RecordingTelemetry` es el fake de los tests.
- **Job:** exporta trazas y logs. Una traza por intento: `process_attempt` con los hijos `convert`, `transcribe` (transcripción y Speech en paralelo), `assess_pronunciation`, `analyze` y `compress_audio`. Los tramos llevan:
  - `attempt.id`, `audio.seconds`, `cost.usd` y `attempt.status`;
  - tokens del LLM, modelo, versión del prompt y si Speech respondió con el recurso de pago.
- **Web:** solo logs y excepciones. Streamlit consulta Cosmos cada 3 s mientras se procesa un intento, y trazar cada lectura sería mucho volumen sin valor.
- **Sin datos personales:** ni el correo ni el texto del usuario van en atributos. Un intento se busca por `attempt.id`, que se ve en Cosmos.
- **Sin instrumentación automática de los SDK de Azure ni de `requests`/`urllib`:** en la primera prueba, las dependencias de Cosmos y Blob traían en el nombre y la URL el id del documento y la ruta del blob, que incluyen el correo. Solo queda `httpx`, que registra la llamada a Azure OpenAI (sin datos del usuario en la URL).
- Se apagan las métricas estándar, los contadores de rendimiento y Live Metrics, para no gastar ingesta.
- **Muestreo `always_on`:** el distro, por defecto, muestrea de forma adaptativa a 5 trazas/s. En la primera prueba en Azure descartó la traza del intento, que llegó justo después de la ráfaga de arranque del job. Con un intento cada tanto no hace falta muestrear.
- El distro ignora `disable_tracing` y `disable_metrics` como argumentos y lee las variables estándar (`OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_TRACES_SAMPLER`). `app_insights.configure` las fija antes de llamarlo.

## Consecuencias

- El costo estimado (`costEstimateUsd`) se calcula en el dominio (`domain/cost.py`) y queda tanto en Cosmos (para el panel de admin) como en la traza.
- El job vacía el exportador antes de terminar (`app_insights.flush`), porque vive pocos minutos.
- Si el tope diario del workspace se alcanza, se pierde telemetría de ese día, pero la app sigue funcionando.
- Una excepción de un SDK de Azure puede traer en su mensaje una ruta con el correo. Llega a Application Insights como cualquier log, con la retención de 30 días del workspace.
- Consultas de ejemplo en `infra/README.md`.
