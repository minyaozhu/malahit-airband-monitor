"""CAT control client for the Malahit DSP2 receiver.

The radio exposes a USB CDC serial port speaking a Kenwood-TS-480-like
protocol. Two quirks verified against real hardware (DSP2, 2026-08):

- Set commands generate responses too, so the input buffer must be
  drained after every set or replies get out of sync with queries.
- Frequency sets across band changes can silently fail (see Hamlib's
  malachite driver), so set_freq verifies by read-back and retries once.
"""

from __future__ import annotations

import glob
import re
import threading
import time

import serial

MODES = {1: "LSB", 2: "USB", 3: "CW", 4: "FM", 5: "AM"}
MODE_IDS = {name: num for num, name in MODES.items()}

BAUD = 19200


def find_port() -> str:
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        raise RuntimeError(
            "No /dev/cu.usbmodem* serial port found - is the Malahit plugged in?"
        )
    return ports[0]


class MalahitCAT:
    def __init__(self, port: str | None = None):
        self.port = port or find_port()
        self.ser = serial.Serial(
            self.port, BAUD, bytesize=8, parity="N", stopbits=1, timeout=1.0
        )
        self.ser.rts = True
        self.ser.dtr = True
        self._lock = threading.Lock()
        time.sleep(0.2)
        self.ser.reset_input_buffer()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    # -- low level ---------------------------------------------------------

    def _drain(self, wait: float = 0.25) -> None:
        """Discard pending bytes (radio echoes responses to set commands)."""
        time.sleep(wait)
        n = self.ser.in_waiting
        if n:
            self.ser.read(n)

    def _query(self, cmd: str, pattern: str, tries: int = 3) -> re.Match:
        for _ in range(tries):
            self.ser.reset_input_buffer()
            self.ser.write(cmd.encode())
            deadline = time.monotonic() + 2.0
            buf = b""
            while time.monotonic() < deadline:
                buf += self.ser.read_until(b";")
                m = re.search(pattern, buf.decode(errors="ignore"))
                if m:
                    return m
        raise TimeoutError(f"no response to {cmd!r}")

    # -- public API --------------------------------------------------------

    def get_freq(self) -> int:
        with self._lock:
            return int(self._query("FA;", r"FA(\d{11});").group(1))

    def set_freq(self, hz: int, verify: bool = True, tolerance: int = 0) -> int:
        """Tune to hz; returns the frequency the radio actually reports.

        The radio floors the commanded frequency onto its currently
        selected tuning-step grid, so the result is often below hz by up
        to one step; pass that step as tolerance to avoid a pointless
        retry. verify=False skips the read-back entirely so interactive
        dragging stays responsive (the caller's poll corrects any drift).
        """
        hz = int(hz)
        with self._lock:
            if not verify:
                self.ser.write(f"FA{hz:011d};".encode())
                self._drain(0.05)
                return hz
            for _ in range(2):
                # Two commands with DIFFERENT values, back to back. Measured
                # on this radio: coming down from the 400 MHz - 2 GHz segment
                # it clamps at 379,997,500 and a single command never crosses,
                # no matter how long you wait or how often you repeat the same
                # value - a repeat of the frequency it already holds is
                # ignored. Sending hz+1 first forces a real retune. Hamlib's
                # malachite driver uses the same trick for band changes.
                self.ser.write(f"FA{hz + 1:011d};".encode())
                self._drain(0.25)
                self.ser.write(f"FA{hz:011d};".encode())
                self._drain(0.35)
                actual = int(self._query("FA;", r"FA(\d{11});").group(1))
                if abs(actual - hz) <= tolerance:
                    break
            return actual

    # Steps the radio offers; the active one is chosen per mode on the device.
    STEP_CANDIDATES = (10, 50, 100, 500, 1000, 2500, 5000,
                       9000, 10_000, 12_500, 25_000, 50_000, 100_000)

    def measure_step(self) -> int:
        """Measure the radio's active tuning step, restoring the frequency.

        Commands increasing offsets until the radio actually moves; the
        first offset that produces movement is the step. Takes ~1-4 s.
        """
        base = self.get_freq()
        step = 0
        try:
            for cand in self.STEP_CANDIDATES:
                self.set_freq(base + cand, verify=False)
                time.sleep(0.35)
                got = self.get_freq()
                if got != base:
                    step = abs(got - base)
                    break
        finally:
            self.set_freq(base, verify=False)
            time.sleep(0.3)
        return step

    def get_mode(self) -> int:
        with self._lock:
            return int(self._query("MD;", r"MD(\d);").group(1))

    def set_mode(self, mode: int) -> None:
        with self._lock:
            self.ser.write(f"MD{int(mode)};".encode())
            self._drain(0.3)
