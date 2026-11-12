#!/bin/sh
set -e

WEB_APP=/app/src/speak2mytrainer/entrypoints/web.py

case "$S2MT_MODE" in
  web)
    exec streamlit run "$WEB_APP" \
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
