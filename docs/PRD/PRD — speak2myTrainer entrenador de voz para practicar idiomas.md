# PRD — speak2myTrainer: entrenador de voz para practicar idiomas

Nov 11, 2026 · @Marco Rojas

## Resumen y objetivo

speak2myTrainer es una app web, móvil primero y 100% Python, para practicar inglés hablado: grabas o subes una respuesta de 10 s a 10 min y recibes métricas de fluidez, muletillas, errores gramaticales, pronunciación y una versión mejorada que puedes escuchar y volver a intentar.

- **Problema:** practicar speaking sin profesor no da feedback objetivo; no sabes cuántas muletillas usas, qué errores repites ni si mejoras entre intentos.
- **Resultado esperado:** un ciclo corto de *grabar → analizar → corregir → repetir* con historial y comparación explícita entre intentos.
- **Doble propósito:** herramienta real para uso personal y de amigos (meta de pasar de B1 a C1 para empleo remoto) y proyecto de portafolio que demuestre IA generativa, servicios de voz de Azure, IaC y CI/CD.
- **Restricciones duras:** solo Python, Azure, tope de **15 USD/mes**, escalado a cero aceptando arranque en frío.

## Usuarios, alcance y no-objetivos

El producto es para un grupo cerrado de menos de 20 personas, hispanohablantes que practican inglés, que entran con su cuenta de Google y solo si su correo está en una lista blanca.

| Perfil | Uso típico | Necesidad clave |
| --- | --- | --- |
| Marco (dueño y admin) | Respuestas de entrevista técnica para empleo remoto | Feedback preciso y comparación entre intentos |
| Amigos invitados | Opiniones, presentaciones, conversación libre | Interfaz simple desde el celular |
| Reclutador o revisor de portafolio | Lee el repo y prueba una demo | Arquitectura clara, IaC, CI/CD y README |

**Dentro del alcance:** inglés como idioma practicado; explicaciones en español por defecto o en el idioma practicado; grabación en navegador y subida de archivo; historial con intentos agrupados.

**Fuera del alcance (por ahora):** banco de preguntas sugeridas, gráficas de progreso en el tiempo, otros idiomas practicados, conversación en tiempo real con un tutor de voz, app nativa, registro abierto al público.

## Flujo del usuario

El ciclo es crear una práctica, grabar, decidir si se envía, ver el análisis y repetir; descartar antes de enviar no consume cuota ni deja rastro.

&#91;embedded content: flujo del usuario · 6 pasos, 1 decisión\]

Reintentar descarta la grabación antes de procesarla. Repetir crea un nuevo intento en la misma práctica, y su análisis recibe el intento anterior como contexto para la comparación.

## Requisitos funcionales

Los requisitos marcados MVP bastan para que la app sea útil de punta a punta; el resto llega en fases posteriores.

| ID | Requisito | Fase |
| --- | --- | --- |
| RF-01 | Login con Google; solo entran correos en lista blanca; el admin agrega o quita correos | MVP |
| RF-02 | Crear una práctica con caja de contexto opcional (pregunta, tema u opinión y situación) | MVP |
| RF-03 | Grabar audio desde el navegador móvil con iniciar, detener y escuchar antes de enviar | MVP |
| RF-04 | Subir un archivo pregrabado (.m4a, .mp3, .wav, .ogg, .webm, .aac) | MVP |
| RF-05 | Validar duración entre 10 s y 10 min antes de procesar; rechazar con mensaje claro | MVP |
| RF-06 | **Reintentar:** descartar la grabación antes de analizarla, sin guardar nada | MVP |
| RF-07 | Procesar en segundo plano y mostrar estado (en cola, transcribiendo, analizando, listo, error) | MVP |
| RF-08 | Métricas: duración, palabras, WPM, muletillas por minuto, reinicios de frase | MVP |
| RF-09 | Muletillas con cita textual y tipo, y lista de usos válidos no contados | MVP |
| RF-10 | Errores gramaticales con cita, corrección, explicación y severidad (error, sugerencia, estilo) | MVP |
| RF-11 | Versión mejorada que conserva la voz del usuario a un nivel alcanzable (B2 aprox.) | MVP |
| RF-12 | Historial por usuario: prácticas, intentos, audio y resultado; borrar práctica o todo el historial | MVP |
| RF-13 | Puntajes de pronunciación, fluidez y prosodia con Azure AI Speech y palabras mal pronunciadas | Fase 2 |
| RF-14 | **Repetir:** nuevo intento sobre la misma práctica, con métricas propias | Fase 2 |
| RF-15 | Comparación explícita contra el intento anterior (qué mejoró, qué empeoró, sugerencias adoptadas) | Fase 2 |
| RF-16 | Escuchar la versión mejorada con voz sintética (Azure TTS), en caché por intento | Fase 2 |
| RF-17 | Ocultar o difuminar la versión mejorada mientras se graba un nuevo intento | Fase 2 |
| RF-18 | Preferencias: idioma de explicaciones (español por defecto) e idioma practicado | MVP (solo inglés practicado) |
| RF-19 | Cuota por usuario (minutos de audio al mes) y bloqueo al alcanzarla | MVP |
| RF-20 | Gráficas de progreso en el tiempo y banco de preguntas | Fase 4 |

## Formato del análisis

Cada intento produce un resultado con seis bloques, validado con el ejemplo real de Marco y aprobado tal cual, más audio TTS y modo ocultar.

**Entrada de ejemplo.** Contexto: *Entrevista para backend developer remoto. Pregunta: Tell me about a challenging project you worked on.* Fragmento: *"well i once participated on a project where we build a eemm a system based on a RAG architecture to help eployees of a company to answer … humm dubts and any question related to the company. So the client needed to manage users and roles to avoid some employees to ask question … Uhmm so we needed to implement a security system … a strategy that helps humm to helps retrieve specific information"*

1. **Métricas:** duración, palabras, WPM con referencia (120–150 en entrevista), muletillas por minuto, reinicios, y puntajes de pronunciación, fluidez y prosodia (0–100).
2. **Muletillas detectadas:** cita con la muletilla resaltada y su tipo (pausa de duda, duda con reinicio, muletilla léxica). Debajo, **usos válidos no contados** con su motivo, por ejemplo *"Well, I once…"* como apertura y *"So the client needed…"* como conector.
3. **Errores gramaticales:** tabla de dijiste, corrección, por qué y tipo (Error, Sugerencia, Estilo). Ejemplos: *participated on* → *in*; *we build* → *we built*; *to avoid some employees to ask* → *to prevent some employees from asking*; *doubts* → *questions* como falso amigo (Sugerencia).
4. **Pronunciación:** palabras con puntaje bajo y lo que se oyó, por ejemplo *employees* (falta la /m/) y *doubts* (la b es muda).
5. **Versión mejorada:** conserva contenido y tono, sube a B2 alcanzable; botón para escucharla (TTS) y para ocultarla o difuminarla.
6. **Para tu próximo intento:** tres acciones concretas. Desde el segundo intento este bloque se vuelve la comparación: errores corregidos, muletillas antes y después, sugerencias adoptadas.

El LLM devuelve un JSON con esquema fijo (Structured Outputs) y la interfaz lo pinta; así el formato no depende de la redacción del modelo:

```json
{
  "fillers": [{"quote": "we build a eemm a system", "token": "eemm", "type": "hesitation"}],
  "valid_non_fillers": [{"quote": "Well, I once", "token": "well", "reason": "discourse opener"}],
  "grammar": [{"quote": "participated on a project", "fix": "participated in a project", "why": "...", "severity": "error"}],
  "improved_version": "...",
  "next_steps": ["...", "...", "..."],
  "comparison": null
}
```

## Requisitos no funcionales y criterios de calidad

El criterio de calidad número uno es cero falsos positivos: la herramienta pierde la confianza del usuario si marca como error inglés coloquial válido o si cuenta como muletilla un uso legítimo.

**Calidad del análisis**

- **Muletillas por contexto, nunca por palabra clave.** *like*, *you know*, *so*, *well*, *actually*, *basically* solo cuentan si no cumplen función gramatical. Cada detección trae cita; cada uso descartado se muestra en "usos válidos".
- **Gramática en registro conversacional.** *gonna*, *wanna*, empezar con *So*, contracciones y elipsis no son errores. Lo dudoso se clasifica como Sugerencia o Estilo, nunca como Error.
- **Transcripción literal.** El transcriptor debe conservar *um*, *uh*, *eh* y repeticiones; si no, el conteo de muletillas es cero por construcción.
- **Set de evaluación** de 30–50 frases ambiguas etiquetadas a mano (*I like coffee* frente a *it was, like, huge*), ejecutado en CI cada vez que cambia el prompt. Meta: 0 falsos positivos en Error y en muletillas, al menos 90% de recall.

**Operación**

| Aspecto | Objetivo |
| --- | --- |
| Duración de audio | 10 s a 10 min |
| Tiempo de análisis | \~0.5× la duración del audio más el arranque del job (\~3 min para 5 min de audio). Decidido el 12-nov-2026: Speech F0 procesa a ese ritmo con una sola solicitud a la vez (ADR 0002) |
| Disponibilidad | Mejor esfuerzo; escalado a cero |
| Costo | ≤ 15 USD/mes total, con alertas de presupuesto en Azure al 50%, 80% y 100% |
| Seguridad | HTTPS, login Google, lista blanca, secretos en Key Vault o variables seguras, identidad administrada hacia los servicios de Azure |
| Privacidad | Audios en contenedor privado; acceso solo con URL SAS de corta duración; el usuario puede borrar su historial |
| Retención | Indefinida hasta que el usuario borre |
| Dispositivos | Chrome Android y Safari iOS como objetivos principales; escritorio como secundario |
| Portafolio | Repo público, IaC en Bicep, CI/CD con GitHub Actions, tests, README con diagrama |

## Evaluación de opciones tecnológicas

Recomendación: Streamlit en Azure Container Apps con autenticación integrada de Google, Cosmos DB en nivel gratuito, Blob Storage, y un análisis híbrido con Azure AI Speech para la acústica y un modelo mini de Azure OpenAI para el texto. Precios y fechas de retiro consultados el 11 de noviembre de 2026.

### Interfaz (100% Python)

| Opción | Grabación en móvil | Login Google | Control de UI | Veredicto |
| --- | --- | --- | --- | --- |
| **Streamlit** | Nativa con `st.audio_input` (WAV, 16 kHz por defecto); `st.file_uploader` para archivos | `st.login` con OIDC o cabeceras de Easy Auth | Medio; el modelo de rerun limita interacciones finas | **Recomendada para MVP**: menos código y todo Python |
| NiceGUI | Sin componente nativo; requiere \~50 líneas de JS con MediaRecorder | Por cuenta propia (Authlib) o Easy Auth | Alto; corre sobre FastAPI y permite exponer API REST | Alternativa si Streamlit se queda corto |
| Reflex | Componente comunitario de captura de audio | Por cuenta propia | Alto; compila a React | Descartada: build con Node, dos puertos, imagen más pesada |
| Gradio | `gr.Audio` con micrófono, funciona en móvil | OAuth orientado a Hugging Face | Bajo para una app multipágina con historial | Descartada: pensada para demos, no apps |

Regla de diseño: la lógica vive en un núcleo hexagonal independiente de la UI y de Azure (ver Arquitectura propuesta); migrar a NiceGUI o FastAPI, o cambiar de modelo, es escribir un adaptador nuevo.

### Transcripción

El panorama de modelos cambió en 2026: en Azure, `whisper@001` se retira el 15 de diciembre de 2026 y las versiones 2025-03-20 de `gpt-4o-transcribe` y `gpt-4o-mini-transcribe` ya se retiraron el 15 de octubre de 2026. **Whisper ya no es una opción válida para un proyecto nuevo.**

| Opción | Conserva muletillas | Marcas de tiempo por palabra | Costo aprox. | Retiro en Azure |
| --- | --- | --- | --- | --- |
| **`gpt-4o-mini-transcribe` (2025-12-15)** | Se puede inducir con un prompt de estilo verbatim; validar en el spike | No (solo texto) | \~0.003 USD/min | 15 jun 2027 |
| Azure AI Speech STT (texto léxico) | Parcial; validar si conserva *um/uh* | Sí | Incluido en Speech (ver abajo) | Servicio, no modelo |
| `whisper@001` | Tiende a limpiar muletillas | Con `verbose_json` | \~0.006 USD/min | 15 dic 2026: **descartado** |

**Resultado del spike (12-nov-2026):** ni `gpt-4o-mini-transcribe` ni `gpt-transcribe` conservan las hesitaciones, ni siquiera con prompt verbatim; Speech léxico sí. Se adopta un esquema híbrido: ver ADR 0002.

### Pronunciación y fluidez acústica

**Azure AI Speech, evaluación de pronunciación no guionizada** (sin texto de referencia): devuelve puntajes de pronunciación, precisión, fluidez y prosodia; por palabra, el tipo de error (pronunciación incorrecta, pausa inesperada, pausa faltante, monotonía). Restricciones verificadas:

- La prosodia solo existe para `en-US`; en otros idiomas no habrá ese puntaje.
- Para audios de más de 30 s se usa reconocimiento continuo del Speech SDK (sin límite de duración).
- La evaluación de contenido (vocabulario, gramática, tema) fue retirada del SDK desde la versión 1.46; Microsoft recomienda hacerla con un modelo de chat, que es justo nuestro diseño.
- El texto que reconoce el modo no guionizado es menos preciso que el STT normal; Microsoft sugiere transcribir primero y luego evaluar en modo guionizado con ese texto. Se decide en el spike de la Fase 0.
- Se factura como STT estándar: el nivel gratuito F0 incluye **5 horas de audio al mes**.

### Análisis de texto (LLM)

| Modelo en Azure | Entrada / salida por 1M tokens | Retiro | Nota |
| --- | --- | --- | --- |
| **`gpt-4.1-mini`** | 0.40 / 1.60 USD | 14 abr 2027 | Recomendado: sin tokens de razonamiento, buen seguimiento de esquemas JSON |
| `gpt-5-mini` | 0.25 / 2.00 USD | 9 feb 2027 | Alternativa; el razonamiento eleva la salida y la latencia |

Ambos se retiran en 2027, así que el nombre del deployment es configuración, no código, y el set de evaluación de la Fase 2 valida cualquier cambio de modelo.

Principio: **las métricas numéricas se calculan en Python** (duración, palabras, WPM a partir de marcas de tiempo, conteos). El LLM solo clasifica, explica y reescribe.

### Autenticación

| Opción | Costo | Esfuerzo | Veredicto |
| --- | --- | --- | --- |
| **Easy Auth de Container Apps con Google** | 0 USD | Configuración en portal o Bicep; la app lee la identidad de la cabecera `X-MS-CLIENT-PRINCIPAL` | **Recomendada**: la app nunca maneja tokens |
| `st.login` de Streamlit (OIDC) | 0 USD | `secrets.toml` y Authlib | Respaldo si la cabecera no llega bien por websocket |
| Entra External ID | Gratis hasta 50 mil usuarios activos al mes | Mayor: tenant externo y flujos | Excesivo para menos de 20 usuarios |

La lista blanca y las cuotas se aplican en la app, sobre el correo verificado que entrega Google.

### Cómputo, datos y almacenamiento

| Pieza | Opción elegida | Por qué | Alternativa descartada |
| --- | --- | --- | --- |
| Web | Container Apps, plan Consumption, mínimo 0 réplicas | Cuota gratis mensual de 180 mil vCPU-s, 360 mil GiB-s y 2 M de solicitudes; a cero no cobra | App Service B1 (\~13 USD/mes fijo) |
| Procesamiento | **Container Apps Job** disparado por Azure Storage Queue | Sin cargos en reposo; la web no se queda viva esperando; mismo código con otro entrypoint | Tarea en segundo plano dentro de la web: el escalado a cero puede matarla a mitad |
| Base de datos | **Cosmos DB NoSQL, nivel gratuito** (1,000 RU/s y 25 GB) | Gratis de por vida; ya lo conoces; partición por usuario | Cosmos serverless (no admite el nivel gratuito); Azure SQL |
| Audio y caché TTS | Blob Storage privado, Hot con paso a Cool a los 30 días | Centavos al mes; URLs SAS de corta vida | — |
| Imágenes | GitHub Container Registry (público) | Gratis; ACR Basic costaría \~5 USD/mes, un tercio del presupuesto | Azure Container Registry |
| Secretos | Secretos de Container Apps e identidad administrada | Gratis | Key Vault (opcional, casi gratis) |
| Observabilidad | Log Analytics con muestreo y retención mínima | Primeros 5 GB al mes gratis | — |
| Voz sintética | Azure AI Speech TTS neural | 0.5 M caracteres gratis al mes en F0 | `gpt-4o-mini-tts` (costo por uso) |

## Arquitectura propuesta

Una sola imagen de contenedor Python corre en dos modos: la web de Streamlit, que solo recibe y encola, y un Container Apps Job, que hace el análisis y se apaga; ninguno tiene réplicas mínimas.

&#91;embedded content: arquitectura en Azure · web, cola y job sobre servicios gestionados\]

La web sube el audio a Blob, crea el intento en Cosmos con estado `queued` y encola un mensaje. El job, disparado por la cola, normaliza el audio con ffmpeg, transcribe, evalúa pronunciación, calcula métricas en Python, analiza con el LLM, genera el TTS y escribe el resultado en Cosmos. La web lee el estado en Cosmos y reproduce audio con URLs SAS.

Pipeline del job, en orden:

1. Descargar el audio de Blob y convertirlo a WAV de 16 kHz mono con ffmpeg (acepta .m4a de iPhone, .ogg, .webm, .mp3).
2. Transcripción verbatim con `gpt-4o-mini-transcribe` y evaluación de pronunciación con el Speech SDK en modo continuo; ambas en paralelo.
3. Métricas deterministas en Python: duración, palabras, WPM con las marcas de tiempo de Speech, pausas largas.
4. Llamada al LLM con Structured Outputs: muletillas, usos válidos, gramática, versión mejorada, próximos pasos y, si hay intento anterior, la comparación.
5. TTS de la versión mejorada bajo demanda, en caché en Blob.
6. Actualizar `usedThisMonth` del usuario y marcar el intento como `done`; ante error, `failed` con mensaje y reintento automático una vez.

### Arquitectura del código: hexagonal

El código sigue puertos y adaptadores: el dominio y los casos de uso no conocen Streamlit ni Azure; la web y el job son adaptadores de entrada, y cada servicio de Azure es un adaptador de salida intercambiable. El motivo principal es que los modelos de transcripción y de LLM se retiran en 2027, y así cambiarlos es escribir un adaptador, no tocar la lógica. Detalle y alternativas en el ADR 0001 del repo (`docs/adr/0001-arquitectura-hexagonal.md`).

| Puerto | Responsabilidad | Adaptador Azure | Adaptador de prueba |
| --- | --- | --- | --- |
| `Transcriber` | Audio a texto verbatim | `gpt-4o-mini-transcribe` | Transcripciones fijas |
| `PronunciationAssessor` | Audio a puntajes y errores por palabra | Azure AI Speech, F0 con failover a S0 | Puntajes fijos |
| `TextAnalyzer` | Transcripción, contexto e intento previo a análisis JSON | `gpt-4.1-mini` con Structured Outputs | Respuestas grabadas |
| `SpeechSynthesizer` | Texto a audio | Azure AI Speech TTS | Audio vacío |
| `AudioStorage` | Guardar, leer y firmar URL de audio | Blob Storage con SAS | Carpeta local |
| `PracticeRepository` | Prácticas e intentos | Cosmos DB | En memoria |
| `UserDirectory` | Lista blanca, preferencias y cuotas | Cosmos DB | En memoria |
| `JobQueue` | Encolar un intento para análisis | Storage Queue | Cola en memoria |

```text
src/speak2mytrainer/
  domain/          # entidades y reglas puras: Practice, Attempt, Metrics, cálculo de WPM
  application/     # casos de uso + ports.py
  adapters/
    inbound/       # streamlit_app/, worker_job/
    outbound/      # azure_openai/, azure_speech/, cosmos/, blob/, storage_queue/, fakes/
  bootstrap.py     # raíz de composición: elige adaptadores por entorno
infra/             # Bicep
evals/             # set de frases y runner
docs/adr/          # decisiones de arquitectura
.github/workflows/
```

Regla de dependencias, verificada en CI con import-linter: `domain` no importa nada del proyecto; `application` solo importa `domain`; los adaptadores importan hacia dentro; solo `bootstrap.py` conoce los adaptadores concretos.

## Modelo de datos

Tres contenedores de Cosmos DB particionados por `userId`, de modo que cada consulta del historial lee una sola partición; los binarios viven en Blob y Cosmos solo guarda su ruta.

| Contenedor | Documento | Campos clave |
| --- | --- | --- |
| `users` | Uno por usuario | `id` (correo), `name`, `role` (admin, user), `allowed`, `feedbackLanguage` (`es` por defecto), `practiceLanguage` (`en`), `quota` { `minutesPerMonth`, `usedThisMonth`, `periodStart` } |
| `practices` | Una práctica agrupa intentos | `id`, `userId`, `title`, `context` (texto opcional), `practiceLanguage`, `createdAt`, `attemptCount`, `lastAttemptAt` |
| `attempts` | Un intento analizado | `id`, `userId`, `practiceId`, `number`, `audioBlob`, `durationSec`, `status`, `transcript`, `metrics` { `words`, `wpm`, `fillersPerMin`, `restarts`, `pronScore`, `accuracy`, `fluency`, `prosody` }, `fillers[]`, `validNonFillers[]`, `grammar[]`, `pronunciation[]`, `improvedVersion`, `ttsBlob`, `nextSteps[]`, `comparison` (nulo en el intento 1), `models` { `transcribe`, `llm`, `promptVersion` }, `costEstimateUsd`, `createdAt` |

Decisiones del modelo:

- Un intento descartado con **Reintentar** nunca llega a Cosmos ni a Blob.
- `status` recorre `queued → transcribing → assessing → analyzing → done`, o `failed` con `error`; la UI lo consulta cada pocos segundos.
- `models.promptVersion` permite comparar resultados de distintos prompts y modelos al reevaluar.
- Rutas en Blob: `audio/{userId}/{practiceId}/{attemptId}.wav` y `tts/{userId}/{attemptId}.mp3`.
- Borrar historial elimina los documentos de la partición del usuario y su prefijo en Blob.

## Estimación de costos

Con uso esperado (unos 10 usuarios y 10 horas de audio al mes) el costo ronda 8 USD/mes, dentro del tope de 15 USD; casi todo el gasto es Azure AI Speech, y la infraestructura queda en niveles gratuitos.

| Concepto | Personal (5 h de audio/mes) | Esperado (10 h/mes) | Supuesto |
| --- | --- | --- | --- |
| Azure AI Speech, evaluación de pronunciación | 0 USD | \~5 USD | 5 h gratis en F0; excedente en S0 a \~1 USD/h (confirmar en la calculadora de Azure) |
| Transcripción `gpt-4o-mini-transcribe` | \~0.90 USD | \~1.80 USD | \~0.003 USD/min |
| LLM `gpt-4.1-mini` | \~0.40 USD | \~0.75 USD | \~5k tokens de entrada y \~2.5k de salida por análisis (\~0.006 USD) |
| Azure TTS, Container Apps, Cosmos DB, logs | 0 USD | 0 USD | Dentro de cuotas gratuitas: 0.5 M caracteres, 180 mil vCPU-s, 1,000 RU/s, 5 GB |
| Blob Storage | \~0.10 USD | \~0.30 USD | Audio comprimido a Opus/M4A tras el análisis |
| **Total** | **\~1.5 USD** | **\~8 USD** | Margen de \~7 USD para crecer o probar modelos |

Controles de gasto:

- **Dos recursos de Speech:** uno F0 como primario y uno S0 que solo se usa cuando el F0 agota sus 5 horas (el F0 rechaza solicitudes al llegar al límite; no se puede mezclar en un mismo recurso).
- **Cuota por usuario:** 60 minutos de audio al mes por defecto, editable por el admin. Con 10 usuarios al tope, el gasto llega a \~8 USD.
- **Presupuesto de Azure** con alertas por correo al 50%, 80% y 100% de 15 USD.
- **Evitar costos fijos:** sin ACR (se usa GHCR), sin App Service, sin réplicas mínimas, Cosmos en nivel gratuito (no serverless).
- El F0 de Speech admite una solicitud concurrente; el job procesa la cola en serie, lo cual basta para este volumen.

## Plan por fases

Cinco fases de 6 a 8 semanas en total a tiempo parcial (estimado con \~10 h por semana); la app es usable al cerrar la Fase 1 y el alcance acordado se completa en la Fase 2.

&#91;embedded content: plan por fases · 5 fases, 4 puertas\]

Cada puerta es un criterio verificable; si no se cumple, se corrige antes de avanzar.

### Fase 0 · Spike y fundaciones

- [x] Suscripción, grupo de recursos y presupuesto de 15 USD con alertas
- [x] Speech F0, Azure OpenAI con `gpt-4o-mini-transcribe` y `gpt-4.1-mini`, Cosmos DB con nivel gratuito, Storage
- [x] Spike de transcripción verbatim y de pronunciación con 5 audios reales (ADR 0002 y ADR 0003)
- [x] Probar `st.audio_input` en el celular y la cabecera de Easy Auth en Streamlit (ADR 0004)
- [x] Repo con estructura hexagonal según el ADR 0001, `pyproject.toml`, linters, pytest e import-linter en CI

### Fase 1 · MVP de análisis de texto

- [x] Bicep: entorno de Container Apps, web, job con disparador de cola, Storage, Cosmos, identidad administrada
- [ ] GitHub Actions: tests, build de imagen a GHCR y despliegue (workflows listos; falta correr `scripts/setup-github-oidc.ps1`)
- [x] Easy Auth con Google, lista blanca y rol admin
- [x] Pantallas: nueva práctica con contexto, grabar o subir, reintentar, estado del procesamiento, resultado, historial
- [x] Validación de 10 s a 10 min y conversión con ffmpeg
- [x] Job: transcripción híbrida (ADR 0002), métricas en Python, LLM con esquema JSON (muletillas, usos válidos, gramática, versión mejorada, próximos pasos)
- [x] Preferencia de idioma de explicaciones (español por defecto) y cuota mensual por usuario
- [x] Borrar práctica y todo el historial (adelantado de la Fase 3)
- [ ] Set de evaluación inicial de 30 frases (32 casos; el set de prueba con fragmentos reales tiene 0 FP pero recall de 56% en muletillas y 50% en errores)

### Fase 2 · Pronunciación y repetición

- [ ] Evaluación de pronunciación en el job con failover de F0 a S0
- [ ] Bloque de pronunciación en el resultado y puntajes en las métricas
- [ ] Repetir sobre la misma práctica y comparación con el intento anterior
- [ ] TTS de la versión mejorada en caché y botón para ocultar o difuminar
- [ ] Set de evaluación a 50 frases, ejecutado en CI cuando cambian prompts o modelos

### Fase 3 · Pulido para portafolio

- [ ] Application Insights con trazas por intento (tiempos y costo estimado)
- [ ] Compresión a Opus tras el análisis y regla de ciclo de vida a Cool
- [ ] Borrar práctica y todo el historial
- [ ] Panel de admin: lista blanca, cuotas, gasto del mes
- [ ] README con diagrama, decisiones de arquitectura (ADR) y video demo

### Fase 4 · Expansión (opcional)

- [ ] Gráficas de progreso por usuario
- [ ] Banco de preguntas de entrevista y temas
- [ ] Idiomas practicados adicionales según soporte de pronunciación de Azure
- [ ] API REST con FastAPI como nuevo adaptador de entrada sobre los mismos casos de uso

## Riesgos y decisiones pendientes

El riesgo más alto es técnico y se resuelve en la Fase 0: que el transcriptor borre las muletillas y deje sin sentido la métrica central.

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| La transcripción limpia *um/uh/eh* | Alto: conteo de muletillas en cero | Spike con 5 audios reales: comparar `gpt-4o-mini-transcribe` con prompt verbatim frente al texto léxico de Azure Speech |
| Falsos positivos del LLM en gramática o muletillas | Alto: pérdida de confianza | Prompt con reglas explícitas, salida JSON con cita obligatoria, set de evaluación en CI, temperatura 0 |
| Grabación en Safari iOS falla o pierde audio al bloquear la pantalla | Medio | Subida de archivo como camino alterno; probar en iPhone y Android en la Fase 1 |
| Retiro de modelos en 2027 (transcriptor y LLM) | Medio | Deployment configurable, `promptVersion` en cada intento, set de evaluación para validar el reemplazo |
| Cabecera de Easy Auth no disponible en la sesión de Streamlit | Medio | Validar en Fase 0; respaldo con `st.login` |
| Arranque en frío de 10–20 s al abrir la app | Bajo | Aceptado; mensaje de carga; imagen ligera (`python:3.12-slim` + ffmpeg) |
| Gasto se dispara por un usuario | Bajo | Lista blanca, cuota mensual por usuario, alertas de presupuesto |
| Audio de 10 min en WAV pesa \~19 MB | Bajo | Grabar a 16 kHz mono; comprimir a Opus tras el análisis |

Decisiones pendientes:

- [x] Confirmar Streamlit frente a NiceGUI después del spike de grabación en móvil: **Streamlit** (ADR 0004).
- [x] Elegir entre evaluación de pronunciación no guionizada directa, o transcribir primero y evaluar en modo guionizado con ese texto: **no guionizada, filtrada por alineación con la transcripción** (ADR 0003).
- [x] Motor de transcripción: **híbrido**, `gpt-4o-mini-transcribe` como texto de registro y Speech léxico como evidencia de muletillas (ADR 0002).
- [ ] Confirmar el precio S0 de Speech para la región elegida.
- [x] Definir la región de Azure con todos los servicios disponibles (Speech con evaluación de pronunciación y prosodia, Azure OpenAI con los modelos elegidos): **East US 2**.
- [ ] Nombre público y dominio del proyecto para el portafolio.

## Siguiente acción recomendada

Arrancar la Fase 0 con un notebook o script local que procese 5 grabaciones reales de Marco (incluido el ejemplo de este PRD) por los tres motores y compare resultados antes de escribir la app.

- [ ] Crear recursos mínimos: Speech F0, Azure OpenAI con `gpt-4o-mini-transcribe` y `gpt-4.1-mini`, presupuesto de 15 USD con alertas.
- [ ] Script `spike_transcribe.py`: misma grabación por `gpt-4o-mini-transcribe` (con y sin prompt verbatim) y por Speech STT; contar muletillas conservadas.
- [ ] Script `spike_pronunciation.py`: evaluación no guionizada frente a guionizada sobre un audio de 3–5 min; medir tiempo y costo.
- [ ] Primer prompt de análisis con esquema JSON y 20 frases del set de evaluación.
- [ ] Probar `st.audio_input` en el iPhone y Android de prueba.

## Fuentes

- [Billing in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing): cuota gratuita y escalado a cero.
- [Enable authentication with Google in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication-google)
- [Use pronunciation assessment](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-pronunciation-assessment): modo no guionizado, prosodia solo en-US, retiro de evaluación de contenido.
- [Azure AI Speech pricing](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services): nivel F0 de 5 h STT y 0.5 M caracteres TTS.
- [Pricing of Pronunciation Assessment (Microsoft Q&A)](https://learn.microsoft.com/en-us/answers/questions/5608069/pricing-and-usage-of-pronunciation-assessment-feat): se factura como STT estándar.
- [Azure AI Foundry model deprecations (BenchLM)](https://benchlm.ai/deprecations/azure): fechas de retiro de Whisper, transcriptores y modelos mini.
- [GPT-4.1 mini Azure pricing (AzureSpeed)](https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-4-1-mini): precios por token de `gpt-4.1-mini` y `gpt-5-mini`.
- [GPT-4o Transcribe en Azure (CloudPrice)](https://cloudprice.net/models/azure/gpt-4o-transcribe)
- [Azure Cosmos DB free tier](https://learn.microsoft.com/azure/cosmos-db/free-tier): 1,000 RU/s y 25 GB, no aplica a serverless.
- [st.audio\_input (Streamlit)](https://docs.streamlit.io/develop/api-reference/widgets/st.audio_input)
- [User authentication in Streamlit](https://docs.streamlit.io/develop/concepts/connections/authentication)
