#!/usr/bin/env bash
# Start AEGIS API (.venv; Piper CLI handles TTS on Python 3.13).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
PIPER_BIN="${ROOT}/tools/piper/piper"

if [[ ! -x "${PIPER_BIN}" ]] && ! python3 -c "import onnxruntime" 2>/dev/null; then
  echo "Note: for local TTS, run ./scripts/setup_local_tts.sh (Piper CLI and models)."
  echo "      Alternatively, install Python 3.12 from https://www.python.org/downloads/macos/ into .venv312."
  echo ""
fi

if [[ -f "${ROOT}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/.venv/bin/activate"
elif [[ -f "${ROOT}/.venv312/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/.venv312/bin/activate"
else
  echo "error: create .venv first: python3 -m venv .venv && pip install -r requirements.txt" >&2
  exit 1
fi

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

PORT="${PORT:-8001}"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT}"
