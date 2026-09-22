#!/bin/sh
set -eu

: "${FLIGHT_CALENDAR_EVAL_REPLAY_DIR:?missing replay dir}"
: "${FLIGHT_CALENDAR_EVAL_HTTP_FIXTURE:?missing recorded fixture}"

exec "${FLIGHT_CALENDAR_EVAL_REAL_PYTHON:-python3}" \
  "${FLIGHT_CALENDAR_EVAL_REPLAY_DIR}/bootstrap.py" "$@"
