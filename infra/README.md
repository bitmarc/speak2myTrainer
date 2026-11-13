# Infraestructura (Bicep)

`main.bicep` se despliega a nivel de suscripción y crea:

| Módulo | Recurso | Notas de costo |
| --- | --- | --- |
| (main) | Grupo `rg-speak2mytrainer` y presupuesto de 15 USD con alertas al 50/80/100% | — |
| `monitoring` | Log Analytics, 30 días de retención, tope de 0.16 GB al día | Dentro de los 5 GB gratis |
| `speech` | Azure AI Speech **F0**, sin llaves (Entra) | 5 h de STT y 0.5 M caracteres de TTS gratis |
| `openai` | Azure OpenAI con `gpt-4o-mini-transcribe` (2025-12-15) y `gpt-4.1-mini` (2025-04-14), GlobalStandard | Solo pago por uso |
| `cosmos` | Cosmos DB **nivel gratuito**: DB con 1000 RU/s compartidos, contenedores `users`, `practices` y `attempts` (pk `/userId`), tope de 1000 RU/s en la cuenta | Gratis |
| `storage` | Contenedores privados `audio` y `tts`, cola `attempts` y paso a Cool a los 30 días; sin shared key | Centavos |
| `roles` | Roles de data plane para el desarrollador (Speech User, OpenAI User, Blob/Queue Data Contributor, Cosmos Data Contributor) | — |

Todos los servicios tienen la autenticación local (llaves) deshabilitada. El código usa `DefaultAzureCredential`: en local toma tu sesión de `az login` y en Azure la identidad administrada.

## Desplegar

```powershell
./scripts/deploy-infra.ps1 -WhatIf      # revisar cambios
./scripts/deploy-infra.ps1              # desplegar y generar .env
```

El script toma tu Object ID con `az ad signed-in-user show` y usa como correo de alertas el de tu sesión de az (`-BudgetEmail` lo cambia).

> Los roles de data plane pueden tardar unos minutos en propagarse después del primer despliegue.

## Web y job en Container Apps (módulo `containerapps`, opcional)

Se despliega solo si pasas `-WebImage`. Crea:
- el entorno de Consumption;
- la identidad administrada, compartida por la web y el job, con los mismos roles de data plane;
- la web, con mínimo 0 réplicas;
- el **job** `caj-s2mt-worker`: KEDA lo arranca cuando hay mensajes en la cola `attempts` (regla `azure-queue` autenticada con la identidad), con una ejecución a la vez porque Speech F0 admite una sola solicitud concurrente.

Los dos usan la misma imagen; `S2MT_MODE` (`web` o `job`) decide qué arranca.

1. El workflow `Imagen` publica `ghcr.io/<owner>/speak2mytrainer:<sha>` en cada push a `main`. La primera vez, haz **pública** la imagen en GitHub → Packages → speak2mytrainer → Package settings → Change visibility.
2. Primer despliegue, **sin auth**, para conocer el FQDN:
   ```powershell
   ./scripts/deploy-infra.ps1 -WebImage ghcr.io/<owner>/speak2mytrainer:latest
   ```
   El script imprime el FQDN y el *redirect URI* para Google.
3. En Google Cloud → APIs & Services → Credentials, crea un **OAuth client ID** de tipo *Web application*:
   - Authorized JavaScript origins: `https://<fqdn>`
   - Authorized redirect URIs: `https://<fqdn>/.auth/login/google/callback`
4. Redespliega con Easy Auth y el admin inicial (el script pide el secreto sin mostrarlo):
   ```powershell
   ./scripts/deploy-infra.ps1 -WebImage ghcr.io/<owner>/speak2mytrainer:latest -GoogleClientId <id> -AdminEmail <tu correo de Google>
   ```
   En los siguientes despliegues basta con `-WebImage`: el script reutiliza el client ID, el secreto y el correo del admin que ya tiene la web.

## Telemetría (Application Insights)

`monitoring.bicep` crea `appi-log-...` sobre el workspace de Log Analytics, con su tope diario y sin autenticación local (ADR 0005). Las apps y el desarrollador envían telemetría con Entra (rol *Monitoring Metrics Publisher*). El job escribe una traza por intento; la web solo escribe logs y excepciones.

Consultas en el portal (Application Insights → Logs):

```kusto
// Últimos intentos: duración total, audio y costo estimado
dependencies
| where name == "process_attempt"
| project timestamp, attempt = tostring(customDimensions["attempt.id"]),
    segundos = duration / 1000, audio = todouble(customDimensions["audio.seconds"]),
    usd = todouble(customDimensions["cost.usd"]), success
| order by timestamp desc

// Cuánto tarda cada paso
dependencies
| where name in ("convert", "transcribe", "assess_pronunciation", "analyze", "compress_audio")
| summarize p50 = percentile(duration, 50) / 1000, p95 = percentile(duration, 95) / 1000 by name

// Costo estimado por día
dependencies
| where name == "process_attempt"
| summarize usd = sum(todouble(customDimensions["cost.usd"])), intentos = count() by bin(timestamp, 1d)
```

Para ver la cascada de un intento: Transaction search → buscar el `attempt.id`.

## GitHub Actions sin secretos (OIDC)

`scripts/setup-github-oidc.ps1` se corre una vez, después de desplegar las apps. Crea la app registration `gh-speak2mytrainer` con credenciales federadas para `main` y los pull requests, y le asigna roles mínimos:
- Container Apps Contributor sobre la web;
- Container Apps Jobs Contributor sobre el job;
- Managed Identity Operator sobre la identidad;
- Cognitive Services OpenAI User.

Además guarda los IDs como variables del repo. Con eso:
- `deploy.yml` actualiza la web y el job a la imagen de cada push a `main`;
- `eval.yml` corre el set de evaluación con el LLM real cuando cambian el prompt o los evals.
