"""Check everything the airband tools need, and say how to fix what's missing.

    python -m airband doctor
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import tempfile

import numpy as np

from airband import TRANSCRIBER
from malahit.dsp import save_wav

OK, BAD = "  ok  ", " FAIL "


def check(label: str, ok: bool, fix: str = "") -> bool:
    print(f"[{OK if ok else BAD}] {label}" + ("" if ok else f"\n         fix: {fix}"))
    return ok


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(prog="airband doctor", description=__doc__.splitlines()[0]).parse_args(argv)
    results = []
    try:
        import sounddevice as sd
        results.append(check("Python packages (numpy, sounddevice, pyserial)", True))
    except Exception as e:                                   # pragma: no cover
        results.append(check("Python packages", False, f"pip install -r requirements.txt ({e})"))
        sd = None
    ports = glob.glob("/dev/cu.usbmodem*")
    results.append(check(f"Radio CAT serial port {ports[0] if ports else ''}".strip(), bool(ports),
                         "connect the DSP2 with a USB data cable and switch it on"))
    if sd:
        names = [d["name"] for d in sd.query_devices() if d["max_input_channels"] >= 2]
        iq = [n for n in names if "xxxx 2" in n]
        results.append(check(f"IQ audio input ({iq[0] if iq else 'not found'})", bool(iq),
                             "the DSP2's 2-channel 192 kHz input should appear in Audio MIDI Setup"))
    built = os.path.exists(TRANSCRIBER / "Contents" / "MacOS" / "transcribe")
    results.append(check("Transcriber app built", built, "run tools/build_transcribe.sh"))
    if built:
        with tempfile.TemporaryDirectory() as d:
            wav, out = os.path.join(d, "t.wav"), os.path.join(d, "t.txt")
            save_wav(wav, np.zeros(16_000))
            subprocess.run(["open", "-W", "-n", str(TRANSCRIBER), "--args", wav, out, "en-US"], timeout=90)
            res = open(out).read() if os.path.exists(out) else "no output"
        ready = "No speech" in res or "segments=" in res
        fix = ("turn on System Settings > Keyboard > Dictation" if "Dictation" in res else
               "allow Speech Recognition for Transcribe in System Settings > Privacy & Security"
               if "authorized" in res else res)
        results.append(check("On-device speech recognition", ready, fix))
    print("\nAll set." if all(results) else "\nFix the items marked FAIL, then run this again.")


if __name__ == "__main__":
    main()
