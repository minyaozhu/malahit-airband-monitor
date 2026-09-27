"""Signal-processing helpers shared by the airband tools."""

from __future__ import annotations

import wave

import numpy as np

AUDIO_BW = 4_500    # AM voice bandwidth (Hz)
OUT_FS = 16_000     # output audio rate: what the speech recognizer wants


def lowpass(x: np.ndarray, fs: int, cutoff: float, taps: int = 1023) -> np.ndarray:
    """Windowed-sinc FIR low-pass, zero phase (mode="same")."""
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff / fs * n) * np.hamming(taps)
    return np.convolve(x, h / h.sum(), mode="same")


def am_demodulate(iq: np.ndarray, fs: int, offset: float = 0.0) -> np.ndarray:
    """AM envelope detection of the signal `offset` Hz from the IQ centre.

    Shifts it to 0 Hz, low-pass filters to the voice bandwidth, takes the
    envelope at 16 kHz and removes the carrier's DC and hum. Returns audio
    normalised to 0.9 peak.
    """
    t = np.arange(len(iq)) / fs
    base = iq * np.exp(-2j * np.pi * offset * t) if offset else iq
    base = lowpass(base, fs, AUDIO_BW)
    audio = np.abs(base[:: fs // OUT_FS])
    audio -= lowpass(audio, OUT_FS, 80, taps=801)
    peak = np.abs(audio).max()
    return audio / peak * 0.9 if peak > 0 else audio


def save_wav(path: str, audio: np.ndarray, rate: int = OUT_FS) -> None:
    """Write mono float audio (-1..1) as 16-bit PCM WAV."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
