#!/bin/bash
# render.sh - Convenience wrapper for rendering music videos
#
# Usage:
#   ./render.sh --audio music.mp3 --lyrics lyrics.lrc --title "Song Name"
#   ./render.sh --audio music.mp3 --lyrics-json lyrics.json --title "Song" --output out/mv.mp4
#
# All options are passed through to render.mjs. See render.mjs for full options list.

set -e
cd "$(dirname "$0")"
node render.mjs "$@"
