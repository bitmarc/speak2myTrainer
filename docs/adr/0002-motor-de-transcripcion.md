# ADR 0002 — Motor de transcripción: híbrido mini-transcribe + Speech léxico

- **Estado:** Aceptada
- **Fecha:** 2026-11-12
- **Autor:** Marco
- **Relacionado:** PRD (secciones "Transcripción" y "Riesgos"), ADR 0001, ADR 0003, `spikes/spike_transcribe.py`

## Contexto

El conteo de muletillas es la métrica central del producto y el PRD exige que el transcriptor conserve *um*, *uh*, *eh*, repeticiones y reinicios de frase. Si los limpia, el conteo es cero por construcción.

El spike de la Fase 0 pasó 5 respuestas reales de Marco a preguntas de entrevista (113–245 s cada una, 11.7 min en total) por siete motores o configuraciones disponibles en East US 2. Las hesitaciones se contaron por regex. Como referencia aproximada se tomó `whisper` con prompt verbatim: es el único motor que marca las hesitaciones en posiciones coherentes con Speech.

| Motor | Hesitaciones (5 audios) | Repeticiones y reinicios | Términos técnicos | Latencia (audio de 2 min) |
| --- | --- | --- | --- | --- |
| `gpt-4o-mini-transcribe` 2025-12-15, con y sin prompt verbatim | **0** | Los limpia | Bien (RAG, Entra ID, yet) | ~4 s |
| `gpt-transcribe` 2026-07-28, con y sin prompt | **0** | Los limpia | Bien, pero corrige al hablante (*last privilege* → *least privilege*) | ~4 s |
| Speech *fast transcription* (REST) | **0** | Los limpia; además borra *like*, *So*, *Once* | Bien | ~2 s |
| Speech STT continuo, forma léxica | **13** (um, uh, hmm) | Los conserva (*to to*, *or or*, *this half has*) | Mal (*rock* por RAG, *algae is just* por *always use*, *jet* por *yet*) | ~55 s |
| `whisper` + prompt verbatim | **38** (um, uh, eh, erm) | Los conserva y los marca (*is- is*, *to- to*) | Bien | ~55 s |

Hallazgos:

1. **El prompt verbatim no tiene ningún efecto** en `gpt-4o-mini-transcribe` ni en `gpt-transcribe`.
2. **Whisper es el mejor motor para disfluencias, pero no es una opción:** `whisper@001` se retira en Azure el 15-dic-2026.
3. **Speech no reconoce el *eh* hispano:** lo transcribe como *and*, *an* o *a*. En el audio 2, whisper marca 12 hesitaciones y Speech solo 1.
4. **`gpt-4o-mini-transcribe` corrige tiempos verbales en silencio:** *I work on* pasa a *I worked on*, *we use* a *we used* y *we store* a *we stored*. Speech y whisper conservan la forma original. En cambio, sí conserva *I like learn*, *how is build*, *an standard* y las muletillas léxicas (*like*, *you know*, *Once, I once*).
5. Al alinear con `difflib` el texto de mini con el léxico de Speech, las disfluencias aparecen como **inserciones**: *um*, *uh*, *on the*, *to*, *or*, *this half has*.

## Decisión

Usar dos transcripciones con funciones distintas:

1. **Texto de registro: `gpt-4o-mini-transcribe` (2025-12-15), sin prompt.** Es el texto que ve el usuario y la base para la gramática, la versión mejorada y las citas de errores gramaticales.
2. **Evidencia verbatim: Speech STT con reconocimiento continuo, forma léxica y marcas de tiempo por palabra.** Se usa solo para muletillas, repeticiones, reinicios, WPM y pausas.
3. **Python alinea las dos** (`difflib.SequenceMatcher` por tokens normalizados):
   - Las hesitaciones (*um/uh/hmm/eh/erm*) del texto léxico se cuentan directamente en Python.
   - Las demás inserciones (repeticiones, reinicios, *and* sueltos) se pasan al LLM como **candidatos**; el LLM decide si son disfluencias.
4. **Las citas se validan contra su fuente:**
   - las de muletillas, contra el texto léxico de Speech;
   - las de gramática, solo contra el texto de mini.

   Así, un error de reconocimiento de Speech (*supply the last privilege*) nunca se convierte en un error gramatical.
5. **WPM y pausas** salen de las marcas de tiempo de Speech, en lugar de dividir las palabras entre la duración de ffprobe.

En la Fase 2, la misma llamada a Speech pasa a ser la evaluación de pronunciación no guionizada (ADR 0003). Así se sigue haciendo **una sola pasada de Speech por intento**.

## Consecuencias

**Positivas**

- Las hesitaciones se miden con datos acústicos reales, y el número lo calcula Python, no el LLM.
- El texto que ve el usuario es el más legible y el que mejor reconoce términos técnicos.
- Cambiar el transcriptor de registro sigue siendo cambiar un adaptador y un deployment (ADR 0001).

**Negativas y riesgos aceptados**

- **Se subcuenta el *eh*:** Speech lo convierte en *and/an/a*. Ante la duda no se cuenta, lo que es coherente con la regla de cero falsos positivos. Se revisará cuando Azure publique un motor verbatim (`gpt-realtime-whisper` o `gpt-live-transcribe` usan la API realtime y no se probaron).
- **Se pierden algunos errores de tiempo verbal** que mini corrige. Afecta al recall, no a los falsos positivos. El set de evaluación de la Fase 1 medirá cuánto.
- **Latencia:** Speech continuo procesa a ~0.5× tiempo real, así que un audio de 5 min tarda ~150 s y no cumple el objetivo del PRD de 30–90 s. Se medirá en la Fase 1. Si hace falta, el job partirá el audio en los silencios y reconocerá los trozos en paralelo.
- **Costo:** cada intento consume minutos de Speech, con 5 h al mes gratis en F0 y luego S0. Mini cuesta ~0.003 USD/min.
- **Cambios en el código:**
  - `Transcriber` devuelve el texto de registro.
  - Hace falta un puerto o resultado para la evidencia verbatim: palabras con marcas de tiempo.
  - `to_domain` debe aceptar citas de muletillas contra el texto léxico.
  - El prompt v1 recibe los candidatos de la alineación.

## Alternativas descartadas

- **Solo `gpt-4o-mini-transcribe` o `gpt-transcribe`:** muletillas en cero.
- **`whisper` + prompt verbatim:** el mejor resultado, pero se retira el 15-dic-2026.
- **Solo Speech léxico:** sus errores de reconocimiento producirían errores gramaticales falsos.
- **Speech *fast transcription*:** rápido, pero borra hesitaciones y muletillas léxicas.
