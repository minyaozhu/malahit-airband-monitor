"""Synthetic tests for the AM demodulator: run with `python -m pytest` or `python tests/test_dsp.py`."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from malahit.dsp import OUT_FS, am_demodulate  # noqa: E402

FS = 192_000


def am_signal(tone_hz: float, offset: float = 0.0, seconds: float = 0.5, noise: float = 0.0):
    t = np.arange(int(FS * seconds)) / FS
    carrier = (1 + 0.6 * np.sin(2 * np.pi * tone_hz * t)) * np.exp(2j * np.pi * offset * t)
    rng = np.random.default_rng(0)
    return carrier + noise * (rng.normal(size=t.size) + 1j * rng.normal(size=t.size))


def dominant(audio: np.ndarray) -> float:
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    return float(np.fft.rfftfreq(len(audio), 1 / OUT_FS)[spec.argmax()])


def test_recovers_tone_at_centre():
    assert abs(dominant(am_demodulate(am_signal(1000), FS)) - 1000) < 5


def test_recovers_tone_at_offset():
    assert abs(dominant(am_demodulate(am_signal(700, offset=12_500), FS, offset=12_500)) - 700) < 5


def test_rejects_out_of_band_voice():
    # a station 25 kHz away must not leak into the channel
    audio = am_demodulate(am_signal(1000, offset=25_000) + 1e-3 * am_signal(400), FS)
    assert abs(dominant(audio) - 400) < 5


def test_works_in_noise():
    assert abs(dominant(am_demodulate(am_signal(1200, noise=0.3), FS)) - 1200) < 5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("passed", name)
