# ADR 0003 — Evaluación de pronunciación no guionizada, filtrada por alineación

- **Estado:** Aceptada
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
