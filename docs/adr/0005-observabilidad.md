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
- Las métricas estándar del distro quedan apagadas (`disable_metrics`) para no gastar ingesta.

## Consecuencias

- El costo estimado (`costEstimateUsd`) se calcula en el dominio (`domain/cost.py`) y queda tanto en Cosmos (para el panel de admin) como en la traza.
- El job vacía el exportador antes de terminar (`app_insights.flush`), porque vive pocos minutos.
- Si el tope diario del workspace se alcanza, se pierde telemetría de ese día, pero la app sigue funcionando.
- Consultas de ejemplo en `infra/README.md`.
