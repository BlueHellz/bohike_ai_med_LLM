#!/usr/bin/env python3
"""
Download Piper ONNX voice models into voices/piper/ (gitignored).

Works on macOS and Linux; uses urllib (stdlib) — no extra deps required.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

# HuggingFace paths relative to v1.0.0 tag (must match voices.json model_file names).
_VOICE_HF_PATHS: dict[str, str] = {
    "en_US-lessac-medium.onnx": "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en_US-lessac-medium.onnx.json": "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    "en_US-amy-low.onnx": "en/en_US/amy/low/en_US-amy-low.onnx",
    "en_US-amy-low.onnx.json": "en/en_US/amy/low/en_US-amy-low.onnx.json",
    "en_GB-alan-medium.onnx": "en/en_GB/alan/medium/en_GB-alan-medium.onnx",
    "en_GB-alan-medium.onnx.json": "en/en_GB/alan/medium/en_GB-alan-medium.onnx.json",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _voices_dir() -> Path:
    return _repo_root() / "voices" / "piper"


def _catalog_files() -> list[str]:
    catalog_path = Path(__file__).resolve().parent / "voices.json"
    with catalog_path.open(encoding="utf-8") as f:
        catalog = json.load(f)
    files: list[str] = []
    for entry in catalog.get("voices", []):
        model_file = entry.get("model_file") or f"{entry['id']}.onnx"
        files.append(model_file)
        files.append(f"{model_file}.json")
    return files


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "aegis-local-tts/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc
    tmp.write_bytes(data)
    tmp.replace(dest)


def download_all(force: bool = False) -> int:
    out_dir = _voices_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for filename in _catalog_files():
        rel = _VOICE_HF_PATHS.get(filename)
        if not rel:
            print(f"skip (no HF mapping): {filename}", file=sys.stderr)
            continue
        dest = out_dir / filename
        if dest.is_file() and not force:
            print(f"exists: {dest.name}")
            continue
        url = f"{_HF_BASE}/{rel}"
        print(f"downloading: {filename} …")
        _download(url, dest)
        downloaded += 1
        print(f"  -> {dest}")
    return downloaded


def main(argv: list[str] | None = None) -> int:
    force = "--force" in (argv or sys.argv[1:])
    try:
        n = download_all(force=force)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"done ({n} file(s) downloaded) -> {_voices_dir()}")
    print("Option A: Python 3.12 from https://www.python.org/downloads/macos/ (pip does not install Python)")
    print("  python3.12 -m venv .venv312 && pip install -r local_tts/requirements.txt")
    print('  pip install --no-deps "piper-tts>=1.2.0"')
    print("Option B: ./scripts/setup_local_tts.sh  (Piper CLI; works with Python 3.13 .venv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
