#!/usr/bin/env bash
set -euo pipefail

PY="/usr/local/bin/python"  # this one imports qdrant_client

cmd="${1:-gui}"
shift || true

case "$cmd" in
  gui)        exec /app/startup.sh ;;
  index-all)  exec "$PY" /app/ragctl.py index-all ;;
  index-since)exec "$PY" /app/ragctl.py index-since ;;
  index-post) exec "$PY" /app/ragctl.py index-post "$@" ;;
  status)     exec "$PY" /app/ragctl.py status ;;
  bash|sh)    exec /bin/bash "$@" ;;
  *)          exec "$PY" "$cmd" "$@" ;;
esac
