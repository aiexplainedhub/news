#!/usr/bin/env bash
set -euo pipefail

PY="/usr/local/bin/python"
CMD="${1:-help}"; shift || true

case "$CMD" in
  index-all)   exec "$PY" /app/ragctl.py index-all ;;
  index-since) exec "$PY" /app/ragctl.py index-since ;;
  index-post)  exec "$PY" /app/ragctl.py index-post "$@" ;;
  status)      exec "$PY" /app/ragctl.py status ;;
  help|*)      echo "Usage: index-all | index-since | index-post <id> | status" ;;
esac
