# Malahit Airband Monitor

Scan the VHF airband with a **Malahit DSP2** SDR and **live-transcribe air traffic control** on a Mac, then turn a session into an interactive map and timeline.

**[▶ See it: Quiet Bridge Arrivals](https://minyaozhu.github.io/malahit-airband-monitor/)** shows 30 minutes of NorCal Approach on 135.650 MHz vectoring 11 airliners onto San Francisco runway 28L, reconstructed from what this tool heard. The page also has two short field videos: the radio and live transcripts in the car, and the page playing back the session.

## What it does

1. **`airband scan`** steps across 118–137 MHz in 150 kHz slices of the radio's IQ stream. It keeps only carriers on the 25 kHz channel grid that carry voice, drops the receiver's own spurs (including a whole-MHz comb), ranks channels over several passes, and tunes the radio to the strongest.
2. **`airband live`** watches the tuned channel's carrier to cut out each transmission, AM-demodulates it in software (so the radio's volume and squelch don't matter), saves it as a WAV, and transcribes it **on-device** with Apple's speech recognizer. Transcripts appear a second or two after each transmission ends.
3. **`airband doctor`** checks the radio connection, the IQ audio device and the speech recognizer, and tells you how to fix anything missing.

Example output from `airband live` (raw recognizer text, then what was actually said):

```
[12:34:44] ( 4.4 s, +44 dB) All right, just maintain 3001 to 3000 clear individual runway left unit 2619
    → "…maintain 3,000 until established, cleared visual approach runway 28 left, United 2619"
[12:52:58] ( 5.7 s, +45 dB) Or Cal approach delta 689 out of 846 210 on the speed heading 030
    → "NorCal Approach, Delta 689, out of 8,000 for 6,000, 210 on the speed, heading 030"
```

## Requirements

- **Malahit DSP2** connected by USB. Tested on firmware 2.58.
- **macOS on Apple Silicon.** The transcriber uses Apple's Speech framework.
- **Python 3.11+.**
- **Siri & Dictation turned on** (System Settings → Keyboard → Dictation).

## Quick start

```bash
git clone https://github.com/minyaozhu/malahit-airband-monitor.git
cd malahit-airband-monitor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
tools/build_transcribe.sh              # builds tools/Transcribe.app (once)
.venv/bin/python -m airband doctor     # everything should say "ok"
.venv/bin/python -m airband scan       # ~4 min, leaves the radio on the busiest channel
.venv/bin/python -m airband live       # Ctrl-C to stop
```

The first transcription asks for Speech Recognition permission; allow it. Recordings and transcripts go to `data/recordings/<date>_<time>_<frequency>/`: one WAV and one `.txt` per transmission, plus a running `transcript.txt`.

You can also `pip install -e .` and use the `airband` command directly.

## Repository layout

```
airband/            the tool: scan.py, live.py, doctor.py, python -m airband entry point
malahit/            small radio library: cat.py (CAT control), iq.py (IQ stream), dsp.py (AM demod)
tools/              transcribe.swift + build script for the on-device transcriber app
tests/              synthetic-signal tests for the demodulator (python tests/test_dsp.py)
data/recordings/    the two sessions behind the visualization (WAV + transcripts)
docs/               the visualization (GitHub Pages) and the field videos
```

## Included data

| Session | Channel | Transmissions |
|---|---|---|
| `2026-09-26_1222_127.450MHz` | 127.450 MHz, found by the scan | 5 |
| `2026-09-26_1227_135.650MHz_norcal` | 135.650 MHz, NorCal Approach, SFO arrivals | 169 |

## Things worth knowing

- **Transcripts are rough.** A general-purpose recognizer mangles callsigns, numbers and phraseology ("unit 2619" is "United 2619", "best celebration" is "visual separation"). The audio clips are saved for checking.
- **The DSP2 only sends IQ up to about 262 MHz**, so this works for the VHF airband but not UHF military air.
- **Set frequency before mode.** The radio restores each band's remembered mode on a band change; `scan` handles this for you.
- **The DC spur and a whole-MHz spur comb** from the receiver would show up as false channels; the scanner filters both.
- **Listening to air traffic control is legal in the US**, and this tool only receives. Check your local rules elsewhere.
