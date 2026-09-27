#!/bin/sh
# Build tools/Transcribe.app: on-device speech-to-text used by air_live.py,
# police_live.py and the AM/SSB transcription steps. macOS needs an app
# bundle (with a usage string) to grant Speech Recognition permission, and
# Siri/Dictation must be enabled in System Settings > Keyboard > Dictation.
set -e
cd "$(dirname "$0")"
mkdir -p Transcribe.app/Contents/MacOS
cp Transcribe-Info.plist Transcribe.app/Contents/Info.plist
swiftc -O -target arm64-apple-macos14.0 transcribe.swift -o Transcribe.app/Contents/MacOS/transcribe
codesign -s - --force --deep Transcribe.app
echo "built tools/Transcribe.app"
