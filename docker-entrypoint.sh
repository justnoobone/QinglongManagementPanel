#!/bin/sh
set -eu

cd /qlpanel/backend

python app.py &
BACKEND_PID="$!"

term_handler() {
  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID"
  fi
  nginx -s quit 2>/dev/null || true
}

trap term_handler INT TERM

nginx -g "daemon off;" &
NGINX_PID="$!"

wait "$NGINX_PID"
