Place one optional General MIDI compatible .sf2 file here for AceFlow chord reference rendering.

Recommended starting point:
- Musical Artifacts candidate: artifact 3677
  https://musical-artifacts.com/artifacts/3677
- LiteGM by Caed
- About 15 MB / about 800 samples
- 128 General MIDI banks + 9 drum kits

Practical advice:
- Prefer a small or medium General MIDI .sf2 with clear piano, bass, and pad sounds.
- Do not overdo it with huge/heavy SoundFonts: very large .sf2 files can make reference rendering painfully slow with little real benefit for conditioning.

Preferred behavior:
- 0 .sf2 files: fallback to internal renderer
- 1 .sf2 file: use it
- 2+ .sf2 files: first alphabetical match is used

This folder is resolved relative to the aceflow package directory, next to static/ and vendor/.
