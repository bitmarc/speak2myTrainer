# ADR 0003 — Evaluación de pronunciación no guionizada, filtrada por alineación

- **Estado:** Aceptada; la pasada única se reemplazó por una segunda pasada opcional (13-nov-2026, ver "Revisión tras el gate de la Fase 2")
- **Fecha:** 2026-11-12
- **Autor:** Marco
- **Relacionado:** PRD (sección "Pronunciación y fluidez acústica"), ADR 0002, `spikes/spike_pronunciation.py`

## Contexto

Azure AI Speech evalúa la pronunciación en dos modos:

- **No guionizado:** sin texto de referencia.
- **Guionizado:** con texto de referencia. Microsoft sugiere transcribir primero y evaluar con ese texto.

El spike comparó los dos modos con prosodia en `en-US`, sobre el audio 1 (112 s) y el 2 (245 s). En el modo guionizado se usó como referencia la transcripción de `gpt-4o-mini-transcribe`.

| Audio | Modo | Pron | Precisión | Fluidez | Prosodia | Palabras con problema | Tiempo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | no guionizado | 84.0 | 90.9 | 90.8 | 80.7 | — | 55 s |
| 1 | guionizado | 87.5 | 92.0 | 91.2 | 80.3 | — | 54 s |
| 2 | no guionizado | 84.3 | 90.3 | 92.4 | 80.3 | 16 | 122 s |
| 2 | guionizado | 86.8 | 92.5 | 91.3 | 77.8 | 10 | 119 s |

Hallazgos:

1. **Los puntajes globales son casi iguales** en los dos modos (±3 puntos). El tiempo y los minutos facturables también son iguales: ~0.5× tiempo real y la duración completa del audio.
2. **El modo no guionizado mezcla errores de reconocimiento con errores de pronunciación.** Entre las 16 palabras marcadas del audio 2 aparecen *infield*, *attic*, *kaaba*, *rock* o *pass*, que el hablante nunca dijo. Mostrarlas sería un falso positivo.
3. **El modo guionizado hace desaparecer las hesitaciones.** En el audio 1, el STT normal reconoce 4 (*um, um, uh, umm*) y el no guionizado 3 (*uh, uh, uhm*); el guionizado ninguna, porque las convierte en *a* o *a from*.
4. **Con reconocimiento continuo, el SDK no informa omisiones ni inserciones** (`ErrorType` solo trae `Mispronunciation`). Hay que calcularlas en el cliente con `difflib`, como hace el ejemplo oficial de Microsoft.

## Decisión

- **Una sola pasada de Speech en modo no guionizado**, con prosodia en `en-US`, granularidad de fonema y reconocimiento continuo. Esa misma pasada sirve como evidencia verbatim para las muletillas (ADR 0002).
- **Las palabras con problema se filtran por alineación:** solo se muestra una palabra marcada si coincide (operación `equal` de `difflib`) con una palabra de la transcripción de mini. Lo que Speech reconoció mal se descarta.
- Los puntajes globales (pronunciación, precisión, fluidez y prosodia) se muestran tal cual. La completitud no se muestra, porque sin referencia no significa nada.

## Consecuencias

**Positivas**

- Un solo minuto de Speech por minuto de audio cubre la pronunciación y las muletillas, en lugar de dos pasadas.
- No se muestran errores de pronunciación sobre palabras que el hablante no dijo.

**Negativas y riesgos aceptados**

- **Se pierden algunas hesitaciones** frente al STT normal (3 de 4 en el audio 1). Si el set de evaluación de la Fase 2 muestra una pérdida mayor, se vuelve a dos pasadas (STT normal y evaluación), con el doble de minutos.
- **Se descartan palabras mal pronunciadas que Speech reconoció como otra palabra** (*principle* por *principal*), aunque a veces esa confusión es justo el error de pronunciación. Es coherente con la regla de cero falsos positivos.
- **Misma latencia que en el ADR 0002:** ~0.5× tiempo real, a mitigar con trozos en paralelo si hace falta.

## Alternativas descartadas

- **Guionizado con la transcripción de mini:** sus palabras marcadas son más limpias, pero borra las hesitaciones y obligaría a pagar una segunda pasada de STT.
- **No guionizado sin filtrar:** muestra palabras que el hablante nunca dijo.

## Revisión tras el gate de la Fase 2 (13-nov-2026)

La decisión dejaba abierto un riesgo: si la pasada con evaluación perdía demasiadas hesitaciones, se volvería a dos pasadas. Antes de construir la Fase 2 se midió con los 5 audios de los spikes. La columna "STT normal" es la pasada de la Fase 1 y la columna "con evaluación" es la pasada no guionizada con prosodia; ambas cuentan con `hesitations()` y `repetitions()` de `domain/disfluency.py`.

| Audio | Duración | Hesitaciones (STT normal → con evaluación) | Repeticiones (STT normal → con evaluación) | Pron | Palabras marcadas → mostradas | Tiempo con evaluación |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 112 s | 4 → 3 | 0 → 1 | 84.0 | 7 → 6 | 55 s |
| 2 | 245 s | 1 → 0 | 5 → 6 | 84.3 | 16 → 6 | 119 s |
| 3 | 117 s | 3 → 0 | 5 → 1 | 84.2 | 3 → 2 | 57 s |
| 4 | 117 s | 3 → 1 | 3 → 3 | 85.7 | 8 → 3 | 56 s |
| 5 | 113 s | 2 → 1 | 3 → 1 | 85.1 | 8 → 1 | 55 s |
| **Total** | | **13 → 5 (−62%)** | **16 → 12**, con falsas (*fast*, *personal*, *point*) | | **42 → 18** | |

Hallazgos:

1. **El gate falla.** Con la evaluación activada, Speech pierde el 62% de las hesitaciones (el límite acordado era 25%) y su forma léxica inventa repeticiones. Las muletillas son la métrica central, así que esa pasada no puede alimentarlas.
2. **La evaluación en sí es útil.** Los puntajes son estables (84–86) y el filtro por alineación descarta lo que Speech reconoció mal (*infield*, *rock*, *kaaba*, *anne*, *inflammation*). Las palabras que quedan son plausibles para un hispanohablante (*reliable*, *educational*, *proud*, *developed*, *the*).
3. **La transcripción rápida no es alternativa:** borra las hesitaciones (ADR 0002).
4. **Precio de S0 en East US 2** (API pública de precios, 13-nov-2026): 1 USD por hora de audio de STT estándar por pasada y 15 USD por millón de caracteres de TTS neural.

### Decisión revisada (Marco, 13-nov-2026)

- **La pronunciación es opcional por intento.** El usuario marca "Evaluar también la pronunciación" al enviar, y el intento guarda `assess_pronunciation`.
- **La evaluación es una segunda pasada de Speech, después del reconocimiento normal.** Va en serie, porque F0 admite una sola solicitud a la vez. El estado pasa por `assessing`. Las muletillas siempre salen de la primera pasada, así que no cambian.
- **El filtro por alineación se mantiene:** compara las palabras de la pasada con evaluación contra el texto de `gpt-4o-mini-transcribe`.

Consecuencias:

- Un intento sin pronunciación cuesta y tarda lo mismo que en la Fase 1.
- Con pronunciación, el intento usa el doble de minutos de Speech, y el análisis tarda ~1× la duración del audio en vez de ~0.5×.
- La cuota del usuario sigue contando minutos de audio, no minutos de Speech. Si el gasto de S0 lo pide, se puede descontar doble cuando hay evaluación.

Alternativas descartadas en esta revisión:

- **Dos pasadas siempre, en serie:** duplica la latencia y los minutos de todos los intentos, aunque el usuario no mire la pronunciación.
- **Dos pasadas en paralelo, la evaluación en S0:** mantiene la latencia, pero la evaluación se paga desde el primer minuto.
- **Una sola pasada:** rompe el conteo de muletillas.
