"""Local Piper ONNX text-to-speech (no cloud APIs)."""

import importlib

_synth = importlib.import_module("local_tts.synthesize")

LocalTtsError = _synth.LocalTtsError
default_voice_id = _synth.default_voice_id
list_voices = _synth.list_voices
synthesize = _synth.synthesize
voice_model_paths = _synth.voice_model_paths

__all__ = [
    "LocalTtsError",
    "default_voice_id",
    "list_voices",
    "synthesize",
    "voice_model_paths",
]
