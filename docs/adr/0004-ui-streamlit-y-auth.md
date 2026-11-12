# ADR 0004 — UI en Streamlit con Easy Auth de Container Apps y Google

- **Estado:** Aceptada (UI); auth pendiente de confirmar que la cabecera llega a Streamlit
- **Fecha:** 2026-11-12
- **Autor:** Marco
- **Relacionado:** PRD (secciones "Interfaz" y "Autenticación"), ADR 0001, `adapters/inbound/streamlit_app/probe.py`, `infra/modules/containerapps.bicep`

## Contexto

El PRD recomienda Streamlit para el MVP, con NiceGUI como alternativa, y Easy Auth de Container Apps con Google, con `st.login` como respaldo. Quedaban dos dudas por validar en la Fase 0:

1. ¿`st.audio_input` graba bien en los navegadores móviles objetivo?
2. ¿La identidad de Easy Auth (`X-MS-CLIENT-PRINCIPAL*`) llega a la sesión de Streamlit, que funciona sobre websocket?

Para validarlas se desplegó el probe (`probe.py`) en Container Apps (`ca-s2mt-web`, Consumption, mínimo 0 réplicas, imagen pública en GHCR), primero sin auth y después con Easy Auth y Google (`RedirectToLoginPage`).

## Resultados

- **Grabación en móvil:** Marco grabó desde el celular con `st.audio_input(sample_rate=16000)` y funcionó bien: WAV de 16 kHz mono que se reproduce en la misma página.
- **Subida de archivos:** el probe incluye `st.file_uploader` (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.webm` y `.aac`) como camino alterno. Las notas de voz `.m4a` de los spikes se convierten bien con ffmpeg. Falta probar la subida desde el celular.
- **Easy Auth:** con el cliente OAuth de Google configurado, las peticiones sin sesión reciben 401 o se redirigen al login.
- **Pendiente de confirmar:** que, tras iniciar sesión, el probe muestre "Sesión iniciada como <correo>". Es decir, que `st.context.headers` reciba `X-MS-CLIENT-PRINCIPAL-NAME` y `X-MS-CLIENT-PRINCIPAL`. Si no llegan, la decisión de auth cambia a `st.login` y este ADR se actualiza.

## Decisión

- **UI en Streamlit 1.67** para el MVP. NiceGUI queda descartada mientras Streamlit cubra los flujos.
- **Autenticación con Easy Auth de Container Apps y Google**, definida en Bicep (`authConfig`) y con el secreto como parámetro seguro.
- El adaptador de entrada lee la identidad de `st.context.headers` y entrega al núcleo solo el correo verificado, como `UserId`. La lista blanca y las cuotas se aplican en la app (Fase 1).
- `st.login` queda como respaldo documentado, sin implementar.

## Consecuencias

**Positivas**

- La app nunca maneja tokens ni secretos de OAuth.
- El mismo contenedor sirve en local, donde no hay cabeceras y el adaptador usa un usuario de desarrollo, y en Azure.

**Negativas y riesgos aceptados**

- **La identidad depende de que Easy Auth esté delante de la app.** Si la app se expone sin auth, nadie la autentica. Mitigación: Bicep fuerza `RedirectToLoginPage`, y el adaptador rechaza peticiones sin cabecera cuando `S2MT_ENV=azure`.
- **Arranque en frío de 10–20 s** por escalar a cero. Se acepta.
- **Grabación con la pantalla bloqueada:** el navegador puede pausar el micrófono. El camino alterno es subir el archivo.
