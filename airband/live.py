"""Live transcription of the airband channel the radio is tuned to.

Never retunes. Watches the channel's AM carrier in the IQ stream - it sits
at the centre of the window and jumps 20-40 dB when someone keys up - to
cut out each transmission. Each one is AM-demodulated in software (so the
radio's volume/squelch don't matter), saved as a WAV, and transcribed
on-device by tools/Transcribe.app in a background worker while capture
continues. Transcripts print as they arrive and are appended to
data/recordings/<stamp>/transcript.txt. Runs until stopped (Ctrl-C).

    python -m airband live
    python -m airband live --open-db 10     # more sensitive squelch
"""

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import threading
import time
from collections import deque

import numpy as np

from airband import RECORDINGS, TRANSCRIBER
from malahit.cat import MalahitCAT
from malahit.dsp import am_demodulate, save_wav
from malahit.iq import IQStream

BLOCK = 0.1            # seconds per squelch decision
PREROLL = 0.3          # keep this much before key-up
HANG = 0.7             # carrier must be gone this long to end a transmission
MIN_TX = 0.8           # ignore shorter blips
NFFT = 8192
APP = str(TRANSCRIBER)


def carrier_db(x: np.ndarray, fs: int) -> float:
    """Power within +/-300 Hz of the centre (the tuned channel's carrier)."""
    n = len(x) // NFFT * NFFT
    if n == 0:
        return float("nan")
    p = np.abs(np.fft.fft(x[:n].reshape(-1, NFFT) * np.hanning(NFFT), axis=1)) ** 2
    f = np.fft.fftfreq(NFFT, 1 / fs)
    return float(10 * np.log10(p[:, np.abs(f) <= 300].sum(1).mean() + 1e-20))




def worker(jobs: queue.Queue, log_path: str) -> None:
    while True:
        wav, stamp, dur, lvl = jobs.get()
        out = wav[:-4] + ".txt"
        subprocess.run(["open", "-W", "-n", APP, "--args", wav, out, "en-US"])
        text = open(out).read().split("\n---\n")[0].strip() if os.path.exists(out) else "(no result)"
        if text.startswith("ERROR"):
            text = "(unintelligible)" if "No speech" in text else text
        line = f"[{stamp}] ({dur:4.1f} s, +{lvl:.0f} dB) {text}"
        print(line, flush=True)
        with open(log_path, "a") as fh:
            fh.write(line + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="airband live", description=__doc__.splitlines()[0])
    ap.add_argument("--open-db", type=float, default=15.0,
                    help="carrier rise over idle that counts as a key-up (dB)")
    args = ap.parse_args(argv)

    cat = MalahitCAT()
    freq = cat.get_freq()                         # read-only: never retunes
    cat.close()
    outdir = str(RECORDINGS / (time.strftime("%Y-%m-%d_%H%M_") + f"{freq / 1e6:.3f}MHz"))
    os.makedirs(outdir, exist_ok=True)
    log_path = f"{outdir}/transcript.txt"
    jobs: queue.Queue = queue.Queue()
    threading.Thread(target=worker, args=(jobs, log_path), daemon=True).start()

    iq = IQStream()
    iq.start()
    fs = iq.fs
    idle: deque = deque(maxlen=100)               # ~10 s of idle carrier levels
    pre: deque = deque(maxlen=int(PREROLL / BLOCK))
    tx: list[np.ndarray] = []
    quiet = 0.0
    peak = 0.0
    t_start = None
    print(f"Listening on {freq / 1e6:.3f} MHz - transcripts appear after each "
          f"transmission (Ctrl-C to stop). Log: {log_path}", flush=True)
    try:
        while True:
            time.sleep(BLOCK)
            x = iq.read()
            if not len(x) or (x == 0).mean() > 0.5:
                continue                          # IQ stream silent
            lvl = carrier_db(x, fs)
            base = float(np.median(idle)) if len(idle) >= 10 else lvl
            rise = lvl - base
            if not tx:
                if len(idle) >= 10 and rise >= args.open_db:
                    tx = list(pre) + [x]
                    t_start, quiet, peak = time.time(), 0.0, rise
                else:
                    idle.append(lvl)
                    pre.append(x)
                continue
            tx.append(x)
            peak = max(peak, rise)
            quiet = quiet + BLOCK if rise < args.open_db / 2 else 0.0
            if quiet >= HANG:
                dur = time.time() - t_start - quiet
                if dur >= MIN_TX:
                    stamp = time.strftime("%H:%M:%S", time.localtime(t_start))
                    wav = os.path.abspath(f"{outdir}/{stamp.replace(':', '')}.wav")
                    save_wav(wav, am_demodulate(np.concatenate(tx), fs))
                    jobs.put((wav, stamp, dur, peak))
                tx, pre = [], deque(maxlen=pre.maxlen)
    except KeyboardInterrupt:
        pass
    finally:
        iq.stop()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
