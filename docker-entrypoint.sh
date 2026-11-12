#!/bin/sh
set -e

APP_DIR=/app/src/speak2mytrainer/adapters/inbound

case "$S2MT_MODE" in
  web)
    # Fase 0: la página probe. En la Fase 1 se reemplaza por la app real.
    exec streamlit run "$APP_DIR/streamlit_app/probe.py" \
      --server.port 8501 \
      --server.address 0.0.0.0 \
      --server.headless true \
      --server.maxUploadSize 50 \
      --browser.gatherUsageStats false
    ;;
  job)
    exec python -m speak2mytrainer.entrypoints.job
    ;;
  *)
    echo "S2MT_MODE desconocido: $S2MT_MODE (usa web o job)" >&2
    exit 2
    ;;
esac
