#!/usr/bin/env bash

set -euo pipefail

FOLLOW_LOG=false
if [[ "${1:-}" == "--follow" || "${1:-}" == "-f" ]]; then
  FOLLOW_LOG=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_AGENT_DIR="${REPO_ROOT}/data-agent"
LOG_DIR="${REPO_ROOT}/.logs"
LOG_FILE="${LOG_DIR}/data-agent.log"

mkdir -p "${LOG_DIR}"

if lsof -nP -iTCP:8001 -sTCP:LISTEN >/dev/null 2>&1; then
  OLD_PID="$(lsof -nP -iTCP:8001 -sTCP:LISTEN -t | head -n 1)"
  if [[ -n "${OLD_PID}" ]]; then
    echo "Stopping existing data-agent process: PID ${OLD_PID}"
    kill "${OLD_PID}" || true
    sleep 1
  fi
fi

cd "${DATA_AGENT_DIR}"

if [[ ! -f ".env" ]]; then
  echo "Missing ${DATA_AGENT_DIR}/.env"
  exit 1
fi

echo "Starting data-agent on 127.0.0.1:8001 ..."
set -a
source .env
set +a

nohup env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy \
  uv run uvicorn main:app --host 127.0.0.1 --port 8001 \
  >"${LOG_FILE}" 2>&1 &

NEW_PID=$!
echo "Started data-agent PID: ${NEW_PID}"
echo "Log file: ${LOG_FILE}"
echo "Health check: curl http://127.0.0.1:8001/health"

if [[ "${FOLLOW_LOG}" == "true" ]]; then
  echo "Following logs (Ctrl+C to stop viewing):"
  tail -n 80 -f "${LOG_FILE}"
fi
