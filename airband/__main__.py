"""airband: scan the airband, live-transcribe a channel, or check your setup.

    python -m airband doctor          # check radio, audio device, transcriber
    python -m airband scan            # find active channels, tune the strongest
    python -m airband live            # transcribe the channel the radio is on
"""

from __future__ import annotations

import sys

COMMANDS = {
    "doctor": ("airband.doctor", "check radio, IQ audio device and transcriber"),
    "scan": ("airband.scan", "scan 118-137 MHz and tune to the strongest voice channel"),
    "live": ("airband.live", "live-transcribe the channel the radio is tuned to"),
}


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in COMMANDS:
        print(__doc__.strip())
        print("\ncommands:")
        for name, (_, desc) in COMMANDS.items():
            print(f"  {name:8s} {desc}")
        sys.exit(0 if not argv or argv[0] in ("-h", "--help") else 2)
    import importlib
    importlib.import_module(COMMANDS[argv[0]][0]).main(argv[1:])


if __name__ == "__main__":
    main()
