#!/usr/bin/env bash
# Download Kokoro-82M ONNX assets and install optional Python deps (no torch).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="${ROOT}/voices/kokoro"
RELEASE="model-files-v1.0"
BASE_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/${RELEASE}"
ONNX="${MODEL_DIR}/kokoro-v1.0.onnx"
VOICES="${MODEL_DIR}/voices-v1.0.bin"

echo "==> Kokoro TTS setup (repo: ${ROOT})"
mkdir -p "${MODEL_DIR}"

download() {
  local url="$1"
  local dest="$2"
  if [[ -f "${dest}" ]]; then
    echo "Present: ${dest}"
    return 0
  fi
  echo "==> Downloading $(basename "${dest}") …"
  curl -fsSL --retry 3 --retry-delay 2 "${url}" -o "${dest}.part"
  mv "${dest}.part" "${dest}"
}

download "${BASE_URL}/kokoro-v1.0.onnx" "${ONNX}"
download "${BASE_URL}/voices-v1.0.bin" "${VOICES}"

onnx_mb="$(du -m "${ONNX}" | awk '{print $1}')"
voices_mb="$(du -m "${VOICES}" | awk '{print $1}')"
total_mb=$((onnx_mb + voices_mb))
echo ""
echo "Model assets (~${total_mb} MB total, gitignored under voices/kokoro/):" 
echo "  ${ONNX} (~${onnx_mb} MB)"
echo "  ${VOICES} (~${voices_mb} MB)"

VENV="${ROOT}/.venv312"
if [[ -d "${VENV}" ]]; then
  PIP="${VENV}/bin/pip"
else
  PIP="pip3"
fi

echo ""
echo "==> Installing kokoro-onnx Python deps …"
"${PIP}" install -r "${ROOT}/local_tts/kokoro_requirements.txt"

echo ""
echo "Done. Add to .env:"
echo "  KOKORO_TTS_ENABLED=true"
echo "  LOCAL_TTS_ENABLED=true   # optional; keep Piper as fallback"
echo ""
echo "Test:"
echo "  python3 -c \"from local_tts.kokoro_synthesize import synthesize; print(len(synthesize('Hello')))\""
echo ""
echo "Note: first synthesis loads the ONNX model (~5–15s). Intel Mac + Python 3.13 is supported"
echo "via onnxruntime; if import fails, fall back to Piper (LOCAL_TTS_ENABLED) in test-ui."
