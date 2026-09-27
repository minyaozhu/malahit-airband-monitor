"""Airband (118-137 MHz AM) scanning and live transcription for the Malahit DSP2."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # repository root
TRANSCRIBER = ROOT / "tools" / "Transcribe.app"
RECORDINGS = ROOT / "data" / "recordings"
