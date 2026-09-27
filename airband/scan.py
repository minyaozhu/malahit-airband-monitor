"""Scan the VHF airband (118-137 MHz AM) and list the active channels.

Steps the Malahit DSP2 across the band in 150 kHz jumps and, at each step,
looks for AM carriers in the IQ window. Step centres sit 12.5 kHz off the
25 kHz channel grid, so no channel ever lands on the receiver's DC spur.
Only carriers on the 25 kHz channel grid count. Carriers that turn up at
the same offset from the centre on many steps are receiver spurs and are
dropped, as are carriers that never show voice sidebands (the receiver's
own clean spurs) or sit on a whole MHz (the receiver's reference-clock
comb). The radio is tuned to the strongest remaining modulated signal.

Airband traffic is push-to-talk, so one pass only catches whoever is keyed
up at that instant. Several passes rank channels by how often they were
heard; continuous broadcasts (ATIS/AWOS/VOLMET) score on every pass.

    python -m airband scan                       # 3 passes (~80 s each)
    python -m airband scan --passes 5 --lo 118 --hi 125
"""

from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict

import numpy as np

from malahit.cat import MODE_IDS, MalahitCAT
from malahit.iq import IQStream

STEP = 150_000
HALF_SPAN = 75_000        # use +/-75 kHz of the +/-96 kHz IQ window
GRID = 25_000
NFFT = 16384              # ~11.7 Hz bins
DWELL = 0.35              # seconds of IQ per step
THRESH_DB = 12.0          # carrier must stand this far above the local floor
SPUR_FRACTION = 0.15      # offset seen on >15% of steps => receiver spur
DC_GUARD = 6000           # ignore +/-6 kHz around the window centre
GRID_TOL = 1500           # carrier must sit within this of a 25 kHz channel
MOD_RATIO = 2.0           # sideband PSD vs floor (3 dB) to count as modulated


def tune(cat: MalahitCAT, hz: int) -> int:
    """Fast unverified set within the band, confirmed by one read-back."""
    cat.set_freq(hz, verify=False)
    time.sleep(0.12)
    got = cat.get_freq()
    if abs(got - hz) > GRID:  # stuck: fall back to the verified path
        got = cat.set_freq(hz)
    return got


def carriers(iq: IQStream) -> list[tuple[float, float, bool]]:
    """(offset_hz, dB above floor, modulated) of carriers within +/-HALF_SPAN.

    Offsets within DC_GUARD of the centre are skipped: the DC spur's skirt
    produced false carriers there, and no channel sits closer than 12.5 kHz.
    "modulated" means the 300-3000 Hz sidebands stand above the floor -
    voice does that, the receiver's own clean spurs do not.
    """
    fs = iq.fs
    iq.read()
    time.sleep(0.08)                 # let the retune settle out of the buffer
    iq.read()
    time.sleep(DWELL)
    x = iq.read()
    n = len(x) // NFFT
    if n == 0:
        return []
    win = np.hanning(NFFT).astype(np.float32)
    frames = x[: n * NFFT].reshape(n, NFFT) * win
    p = (np.abs(np.fft.fftshift(np.fft.fft(frames, axis=1), axes=1)) ** 2).mean(0)
    f = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / fs))
    keep = (np.abs(f) <= HALF_SPAN) & (np.abs(f) >= DC_GUARD)
    p, f = p[keep], f[keep]
    db = 10 * np.log10(p + 1e-20)
    floor = np.median(db)
    floor_lin = 10 ** (floor / 10)
    out = []
    order = np.argsort(db)[::-1]
    for i in order:
        if db[i] < floor + THRESH_DB:
            break
        if all(abs(f[i] - o) > 3000 for o, _, _ in out):
            d = np.abs(f - f[i])
            side = p[(d >= 300) & (d <= 3000)]
            modulated = side.size > 0 and side.mean() > MOD_RATIO * floor_lin
            out.append((float(f[i]), float(db[i] - floor), bool(modulated)))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="airband scan", description=__doc__.splitlines()[0])
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--lo", type=float, default=118.0, help="MHz")
    ap.add_argument("--hi", type=float, default=137.0, help="MHz")
    ap.add_argument("--restore", action="store_true",
                    help="return to the original frequency/mode afterwards")
    args = ap.parse_args(argv)

    lo, hi = int(args.lo * 1e6), int(args.hi * 1e6)
    centres = list(range(lo + HALF_SPAN - GRID // 2, hi + HALF_SPAN, STEP))

    cat = MalahitCAT()
    iq = IQStream()
    orig_freq, orig_mode = cat.get_freq(), cat.get_mode()
    cat.set_mode(MODE_IDS["AM"])
    iq.start()

    hits: dict[int, list[float]] = defaultdict(list)     # channel Hz -> levels
    passes_heard: dict[int, set[int]] = defaultdict(set)
    voiced: dict[int, int] = defaultdict(int)              # sightings with sidebands
    offsets: Counter = Counter()
    raw: list[tuple[int, int, float, float, bool]] = []    # pass, ch, off, dB, mod
    off_grid = 0
    print(f"Airband {args.lo:g}-{args.hi:g} MHz: {len(centres)} steps/pass, "
          f"{args.passes} passes\n")
    try:
        for p in range(args.passes):
            t = time.monotonic()
            found = 0
            for c in centres:
                got = tune(cat, c)
                for off, lvl, mod in carriers(iq):
                    abs_hz = got + off
                    if not (lo <= abs_hz <= hi):
                        continue
                    ch = round(abs_hz / GRID) * GRID
                    if abs(abs_hz - ch) > GRID_TOL:
                        off_grid += 1
                        continue
                    offsets[round(off / 500)] += 1
                    raw.append((p, ch, off, lvl, mod))
                    found += 1
            print(f"pass {p + 1}: {found} on-grid carriers in "
                  f"{time.monotonic() - t:.0f} s", flush=True)
    finally:
        iq.stop()

    steps = len(centres) * args.passes
    spurs = {k for k, v in offsets.items() if v > SPUR_FRACTION * steps}
    for p, ch, off, lvl, mod in raw:
        if round(off / 500) in spurs:
            continue
        hits[ch].append(lvl)
        passes_heard[ch].add(p)
        voiced[ch] += mod
    print(f"(ignored {off_grid} off-grid carriers"
          + (f"; receiver spurs at offsets "
             f"{', '.join(f'{k * 0.5:+.1f}' for k in sorted(spurs))} kHz" if spurs else "")
          + ")")

    # The receiver puts a spur on every whole MHz (reference-clock comb); some
    # pass the sideband test, so whole-MHz channels are treated as spurs.
    comb = {ch for ch in hits if ch % 1_000_000 == 0}
    stations = [ch for ch in hits if voiced[ch] and ch not in comb]
    carriers_only = [ch for ch in hits if not voiced[ch] or ch in comb]
    ranked = sorted(stations, key=lambda ch: max(hits[ch]), reverse=True)
    if not ranked:
        print("\nNo modulated airband signals heard.")
    else:
        print(f"\n{'MHz':>8}  {'heard':>7}  {'peak':>6}  note")
        for ch in ranked:
            n = len(passes_heard[ch])
            note = "every pass (ATIS/AWOS?)" if n == args.passes > 1 else ""
            print(f"{ch / 1e6:>8.3f}  {n:>3}/{args.passes:<3}  "
                  f"{max(hits[ch]):>4.0f}dB  {note}")
    if carriers_only:
        print(f"\nUnmodulated carriers, likely receiver spurs (not tuned): "
              + ", ".join(f"{ch / 1e6:.3f}" for ch in sorted(carriers_only)))

    if args.restore or not ranked:
        cat.set_freq(orig_freq)
        cat.set_mode(orig_mode)
        print(f"\nRestored {orig_freq / 1e3:.1f} kHz.")
    else:
        best = ranked[0]
        got = cat.set_freq(best, tolerance=GRID)
        print(f"\nRadio left on {got / 1e6:.3f} MHz AM (strongest modulated "
              f"signal, {max(hits[best]):.0f} dB). Turn the volume up to listen.")
    cat.close()


if __name__ == "__main__":
    main()
