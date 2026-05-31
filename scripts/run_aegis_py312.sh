#!/usr/bin/env bash
# Start AEGIS with Python 3.12 venv (.venv312) for optional in-process Piper/onnxruntime.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [[ ! -d "${ROOT}/.venv312" ]]; then
  echo "error: .venv312 not found — install Python 3.12 from https://www.python.org/downloads/macos/" >&2
  echo "  python3.12 -m venv .venv312 && source .venv312/bin/activate && pip install -r requirements.txt -r local_tts/requirements.txt" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${ROOT}/.venv312/bin/activate"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

PORT="${PORT:-8001}"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT}"
