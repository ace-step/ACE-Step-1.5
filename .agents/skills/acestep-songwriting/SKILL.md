---
name: acestep-songwriting
description: Music songwriting guide for ACE-Step. Provides professional knowledge on writing captions, lyrics, choosing BPM/key/duration, and structuring songs. Use this skill when users want to create, write, or plan a song before generating it with ACE-Step.
allowed-tools: Read
---

# ACE-Step Songwriting Guide

Professional music creation knowledge for writing captions, lyrics, and choosing music parameters for ACE-Step.

## Output Format

After using this guide, produce two things for the acestep skill:
1. **Caption** (`-c`): Style/genre/instruments/emotion description
2. **Lyrics** (`-l`): Complete structured lyrics with tags
3. **Parameters**: `--duration`, `--bpm`, `--key`, `--time-signature`, `--language`

---

## Caption: The Most Important Input

**Caption is the most important factor affecting generated music.**

Supports multiple formats: simple style words, comma-separated tags, complex natural language descriptions.

### Common Dimensions

| Dimension | Examples |
|-----------|----------|
| **Style/Genre** | pop, rock, jazz, electronic, hip-hop, R&B, folk, classical, lo-fi, synthwave |
| **Emotion/Atmosphere** | melancholic, uplifting, energetic, dreamy, dark, nostalgic, euphoric, intimate |
| **Instruments** | acoustic guitar, piano, synth pads, 808 drums, strings, brass, electric bass |
| **Timbre Texture** | warm, bright, crisp, muddy, airy, punchy, lush, raw, polished |
| **Era Reference** | 80s synth-pop, 90s grunge, 2010s EDM, vintage soul, modern trap |
| **Production Style** | lo-fi, high-fidelity, live recording, studio-polished, bedroom pop |
| **Vocal Characteristics** | female vocal, male vocal, breathy, powerful, falsetto, raspy, choir |
| **Speed/Rhythm** | slow tempo, mid-tempo, fast-paced, groovy, driving, laid-back |
| **Structure Hints** | building intro, catchy chorus, dramatic bridge, fade-out ending |

### Caption Writing Principles

1. **Specific beats vague** — "sad piano ballad with female breathy vocal" > "a sad song"
2. **Combine multiple dimensions** — style+emotion+instruments+timbre anchors direction precisely
3. **Use references well** — "in the style of 80s synthwave" conveys complex aesthetic quickly
4. **Texture words are useful** — warm, crisp, airy, punchy influence mixing and timbre
5. **Don't pursue perfection** — Caption is a starting point, iterate based on results
6. **Granularity determines freedom** — Less detail = more model creativity; more detail = more control
7. **Avoid conflicting words** — "classical strings" + "hardcore metal" degrades output
   - **Fix: Repetition reinforcement** — Repeat the elements you want more
   - **Fix: Conflict to evolution** — "Start with soft strings, middle becomes metal rock, end turns to hip-hop"
8. **Don't put BPM/key/tempo in Caption** — Use dedicated parameters instead

---

## Lyrics: The Temporal Script

Lyrics controls how music unfolds over time. It carries:
- Lyric text itself
- **Structure tags** ([Verse], [Chorus], [Bridge]...)
- **Vocal style hints** ([raspy vocal], [whispered]...)
- **Instrumental sections** ([guitar solo], [drum break]...)
- **Energy changes** ([building energy], [explosive drop]...)

### Structure Tags

| Category | Tag | Description |
|----------|-----|-------------|
| **Basic Structure** | `[Intro]` | Opening, establish atmosphere |
| | `[Verse]` / `[Verse 1]` | Verse, narrative progression |
| | `[Pre-Chorus]` | Pre-chorus, build energy |
| | `[Chorus]` | Chorus, emotional climax |
| | `[Bridge]` | Bridge, transition or elevation |
| | `[Outro]` | Ending, conclusion |
| **Dynamic Sections** | `[Build]` | Energy gradually rising |
| | `[Drop]` | Electronic music energy release |
| | `[Breakdown]` | Reduced instrumentation, space |
| **Instrumental** | `[Instrumental]` | Pure instrumental, no vocals |
| | `[Guitar Solo]` | Guitar solo |
| | `[Piano Interlude]` | Piano interlude |
| **Special** | `[Fade Out]` | Fade out ending |
| | `[Silence]` | Silence |

### Combining Tags

Use `-` for finer control, but keep it concise:

```
✅ [Chorus - anthemic]
❌ [Chorus - anthemic - stacked harmonies - high energy - powerful - epic]
```

Put complex style descriptions in Caption, not in tags.

### Caption-Lyrics Consistency

**Models are not good at resolving conflicts.** Checklist:
- Instruments in Caption ↔ Instrumental section tags in Lyrics
- Emotion in Caption ↔ Energy tags in Lyrics
- Vocal description in Caption ↔ Vocal control tags in Lyrics

### Vocal Control Tags

| Tag | Effect |
|-----|--------|
| `[raspy vocal]` | Raspy, textured vocals |
| `[whispered]` | Whispered |
| `[falsetto]` | Falsetto |
| `[powerful belting]` | Powerful, high-pitched singing |
| `[spoken word]` | Rap/recitation |
| `[harmonies]` | Layered harmonies |
| `[call and response]` | Call and response |
| `[ad-lib]` | Improvised embellishments |

### Energy and Emotion Tags

| Tag | Effect |
|-----|--------|
| `[high energy]` | High energy, passionate |
| `[low energy]` | Low energy, restrained |
| `[building energy]` | Increasing energy |
| `[explosive]` | Explosive energy |
| `[melancholic]` | Melancholic |
| `[euphoric]` | Euphoric |
| `[dreamy]` | Dreamy |
| `[aggressive]` | Aggressive |

### Lyric Writing Tips

1. **6-10 syllables per line** — Model aligns syllables to beats; keep similar counts for lines in same position (±1-2)
2. **Uppercase = stronger intensity** — `WE ARE THE CHAMPIONS!` (shouting) vs `walking through the streets` (normal)
3. **Parentheses = background vocals** — `We rise together (together)`
4. **Extend vowels** — `Feeeling so aliiive` (use cautiously, effects unstable)
5. **Clear section separation** — Blank lines between sections

### Avoiding "AI-flavored" Lyrics

| Red Flag | Description |
|----------|-------------|
| **Adjective stacking** | "neon skies, electric hearts, endless dreams" — vague imagery filler |
| **Rhyme chaos** | Inconsistent patterns or forced rhymes breaking meaning |
| **Blurred boundaries** | Lyric content crosses structure tags |
| **No breathing room** | Lines too long to sing in one breath |
| **Mixed metaphors** | Water → fire → flying — listeners can't anchor |

**Metaphor discipline**: One core metaphor per song, explore its multiple aspects.

---

## Music Metadata

**Most of the time, let LM auto-infer.** Only set manually when you have clear requirements.

| Parameter | Range | Description |
|-----------|-------|-------------|
| `bpm` | 30–300 | Slow 60–80, mid 90–120, fast 130–180 |
| `keyscale` | Key | e.g. `C Major`, `Am`. Common keys (C, G, D, Am, Em) most stable |
| `timesignature` | Time sig | `4/4` (most common), `3/4` (waltz), `6/8` (swing) |
| `vocal_language` | Language | Usually auto-detected from lyrics |
| `duration` | Seconds | See duration calculation below |

### When to Set Manually

| Scenario | Set |
|----------|-----|
| Daily generation | Let LM auto-infer |
| Clear tempo requirement | `bpm` |
| Specific style (waltz) | `timesignature=3/4` |
| Match other material | `bpm` + `duration` |
| Specific key color | `keyscale` |

---

## Duration Calculation

### Estimation Method

- **Intro/Outro**: 5-10 seconds each
- **Instrumental sections**: 5-15 seconds each
- **Typical structures**:
  - 2 verses + 2 choruses: 120-150s minimum
  - 2 verses + 2 choruses + bridge: 180-240s minimum
  - Full song with intro/outro: 210-270s (3.5-4.5 min)

### BPM and Duration Relationship

- **Slower BPM (60-80)**: Need MORE duration for same lyrics
- **Medium BPM (100-130)**: Standard duration
- **Faster BPM (150-180)**: Can fit more lyrics, but still need breathing room

**Rule of thumb**: When in doubt, estimate longer. A song too short feels rushed.

---

Note: Lyrics tags (piano, powerful, whispered) are consistent with Caption (piano ballad, building to powerful chorus, intimate).
