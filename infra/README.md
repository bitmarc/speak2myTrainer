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

## Web en Container Apps (módulo `containerapps`, opcional)

Se despliega solo si pasas `-WebImage`. Crea el entorno de Consumption, la identidad administrada (compartida con el job de la Fase 1, con los mismos roles de data plane) y la web con mínimo 0 réplicas.

1. El workflow `Imagen` publica `ghcr.io/<owner>/speak2mytrainer:<sha>` en cada push a `main`. La primera vez, haz **pública** la imagen en GitHub → Packages → speak2mytrainer → Package settings → Change visibility.
2. Primer despliegue, **sin auth**, para conocer el FQDN:
   ```powershell
   ./scripts/deploy-infra.ps1 -WebImage ghcr.io/<owner>/speak2mytrainer:latest
   ```
   El script imprime el FQDN y el *redirect URI* para Google.
3. En Google Cloud → APIs & Services → Credentials, crea un **OAuth client ID** de tipo *Web application*:
   - Authorized JavaScript origins: `https://<fqdn>`
   - Authorized redirect URIs: `https://<fqdn>/.auth/login/google/callback`
4. Redespliega con Easy Auth (el script pide el secreto sin mostrarlo):
   ```powershell
   ./scripts/deploy-infra.ps1 -WebImage ghcr.io/<owner>/speak2mytrainer:latest -GoogleClientId <id>
   ```
