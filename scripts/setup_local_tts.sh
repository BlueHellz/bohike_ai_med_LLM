#!/usr/bin/env bash
# Homebrew-free local Piper TTS setup: Piper CLI, phonemize libs, voice models.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIPER_DIR="${ROOT}/tools/piper"
PIPER_BIN="${PIPER_DIR}/piper"
LIB_DIR="${PIPER_DIR}/lib"
PIPER_RELEASE="2023.11.14-2"
PHON_RELEASE="2023.11.14-4"

os="$(uname -s)"
arch="$(uname -m)"
if [[ "${os}" == "Darwin" ]]; then
  case "${arch}" in
    x86_64)
      piper_asset="piper_macos_x64.tar.gz"
      phon_asset="piper-phonemize_macos_x64.tar.gz"
      ;;
    arm64)
      piper_asset="piper_macos_aarch64.tar.gz"
      phon_asset="piper-phonemize_macos_aarch64.tar.gz"
      ;;
    *) echo "Unsupported macOS architecture: ${arch}" >&2; exit 1 ;;
  esac
elif [[ "${os}" == "Linux" ]]; then
  case "${arch}" in
    x86_64)
      piper_asset="piper_linux_x86_64.tar.gz"
      phon_asset="piper-phonemize_linux_x86_64.tar.gz"
      ;;
    aarch64|arm64)
      piper_asset="piper_linux_aarch64.tar.gz"
      phon_asset="piper-phonemize_linux_aarch64.tar.gz"
      ;;
    *) echo "Unsupported Linux architecture: ${arch}" >&2; exit 1 ;;
  esac
else
  echo "Unsupported OS: ${os}" >&2
  exit 1
fi

echo "==> Local TTS setup (repo: ${ROOT})"

if [[ ! -x "${PIPER_BIN}" ]]; then
  url="https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}/${piper_asset}"
  echo "==> Downloading Piper CLI (${piper_asset}) …"
  mkdir -p "${ROOT}/tools"
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' EXIT
  curl -fsSL "${url}" -o "${tmpdir}/piper.tgz"
  tar -xzf "${tmpdir}/piper.tgz" -C "${ROOT}/tools"
  if [[ -x "${ROOT}/tools/piper/piper/piper" && ! -x "${PIPER_BIN}" ]]; then
    shopt -s dotglob
    mv "${ROOT}/tools/piper/piper/"* "${PIPER_DIR}/"
    rmdir "${ROOT}/tools/piper/piper" 2>/dev/null || true
  fi
fi

if [[ ! -x "${PIPER_BIN}" ]]; then
  echo "error: Piper executable missing at ${PIPER_BIN}" >&2
  exit 1
fi
echo "Piper CLI: ${PIPER_BIN}"

need_libs=1
if [[ -f "${LIB_DIR}/libespeak-ng.1.dylib" || -f "${LIB_DIR}/libespeak-ng.so.1" ]]; then
  need_libs=0
fi
if [[ "${need_libs}" -eq 1 ]]; then
  phon_url="https://github.com/rhasspy/piper-phonemize/releases/download/${PHON_RELEASE}/${phon_asset}"
  echo "==> Downloading Piper phonemize runtime (${phon_asset}) …"
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' EXIT
  curl -fsSL "${phon_url}" -o "${tmpdir}/phon.tgz"
  tar -xzf "${tmpdir}/phon.tgz" -C "${tmpdir}"
  mkdir -p "${LIB_DIR}"
  if [[ -d "${tmpdir}/piper-phonemize/lib" ]]; then
    cp -f "${tmpdir}/piper-phonemize/lib/"*.dylib "${LIB_DIR}/" 2>/dev/null || true
    cp -f "${tmpdir}/piper-phonemize/lib/"*.so* "${LIB_DIR}/" 2>/dev/null || true
  fi
fi

DEFAULT_MODEL="${ROOT}/voices/piper/en_US-lessac-medium.onnx"
if [[ ! -f "${DEFAULT_MODEL}" ]]; then
  echo "==> Downloading voice models …"
  python3 "${ROOT}/local_tts/download_voices.py"
else
  echo "Voice models present under voices/piper/"
fi

echo ""
echo "Done. Enable LOCAL_TTS_ENABLED=true in .env and restart the API."
echo "Test: python3 -c \"from local_tts import synthesize; print(len(synthesize('Hello')))\""
echo ""
echo "pip does not install Python. Optional: Python 3.12 from https://www.python.org/downloads/macos/"
