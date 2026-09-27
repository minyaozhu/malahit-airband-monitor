"""IQ capture from the Malahit DSP2's USB audio interface.

The radio enumerates as a class-compliant USB audio device. Its IQ
interface is the 2-channel input at 192 kHz (descriptor string "xxxx 2"
on current firmware); left channel = I, right channel = Q.
"""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd


def find_device() -> tuple[int, int]:
    """Return (device_index, sample_rate) of the Malahit IQ input."""
    best = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 2:
            continue
        fs = int(d["default_samplerate"])
        name = d["name"]
        if "xxxx 2" in name:  # current Malahit firmware descriptor string
            return i, fs
        if fs >= 96_000 and (best is None or fs > best[1]):
            best = (i, fs)
    if best is None:
        raise RuntimeError(
            "No Malahit IQ audio device found (need a 2-ch input at >=96 kHz)"
        )
    return best


class IQStream:
    """Continuously captures IQ into a buffer the GUI drains each frame."""

    def __init__(self, device: int | None = None, fs: int | None = None):
        if device is None or fs is None:
            device, fs = find_device()
        self.device = device
        self.fs = fs
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._discard = int(0.35 * fs)  # skip Core Audio startup silence
        self.stream = sd.InputStream(
            device=device,
            channels=2,
            samplerate=fs,
            dtype="float32",
            blocksize=2048,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status) -> None:
        if self._discard > 0:
            self._discard -= frames
            return
        iq = indata[:, 0].astype(np.complex64)
        iq += 1j * indata[:, 1]
        with self._lock:
            self._chunks.append(iq)
            # cap buffered audio at ~2 s so a stalled GUI can't grow it forever
            while sum(len(c) for c in self._chunks) > 2 * self.fs:
                self._chunks.pop(0)

    def start(self) -> None:
        self.stream.start()

    def stop(self) -> None:
        try:                       # idempotent: the disconnect watchdog and
            self.stream.stop()     # closeEvent may both call this
            self.stream.close()
        except Exception:
            pass

    def read(self) -> np.ndarray:
        """Return all samples captured since the last call."""
        with self._lock:
            if not self._chunks:
                return np.empty(0, dtype=np.complex64)
            chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks)
