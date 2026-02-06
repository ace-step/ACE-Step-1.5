# ACE-Step 1.5 — A Musician's Guide

## What Is This Thing?

ACE-Step is a music-making AI that runs on your own computer. You describe the music you want — the style, the instruments, the mood, the lyrics — and it generates a full song in seconds. Not a loop, not a beat — a complete song with vocals, instruments, and structure.

Unlike cloud services like Suno or Udio, ACE-Step runs locally. You own the software, you own the output, and you can use it offline with no subscription, no rate limits, and no terms of service restrictions.

It's open-source and free.

---

## How Does It Actually Work?

ACE-Step has two "brains" that work together, like a songwriter and a studio engineer:

```
    ┌─────────────────────────────────────────────────────────┐
    │                    YOU (the musician)                   │
    │                                                         │
    │   "I want an upbeat pop song with electric guitars,     │
    │    catchy chorus, female vocals, 120 BPM"               │
    └──────────────────────┬──────────────────────────────────┘
                           │
                    Your description
                           │
                           ▼
    ┌─────────────────────────────────────────────────────────┐
    │              BRAIN 1: The Songwriter (LM)               │
    │                                                         │
    │   Reads your description and thinks about it.           │
    │   Fills in the gaps you didn't specify:                 │
    │     - What key fits this mood? → G Major                │
    │     - What tempo feels right? → 122 BPM                 │
    │     - How should the song be structured?                │
    │     - Where should energy peak?                         │
    │                                                         │
    │   Creates a detailed blueprint of the song.             │
    │                                                         │
    │   (Optional — you can skip this brain for speed,        │
    │    or if you already know exactly what you want.)       │
    └──────────────────────┬──────────────────────────────────┘
                           │
                      Blueprint
                           │
                           ▼
    ┌─────────────────────────────────────────────────────────┐
    │           BRAIN 2: The Studio Engineer (DiT)            │
    │                                                         │
    │   Takes the blueprint and builds the actual audio.      │
    │   Starts with pure noise (like static on a TV)          │
    │   and gradually shapes it into music — step by step.    │
    │                                                         │
    │   Each step removes a layer of noise and adds           │
    │   detail: instruments come into focus, vocals           │
    │   emerge, drums tighten up, mix clears.                 │
    │                                                         │
    │   After 8 steps (fast mode) or 50 steps (quality        │
    │   mode), you have a finished song.                      │
    └──────────────────────┬──────────────────────────────────┘
                           │
                     Finished audio
                           │
                           ▼
    ┌─────────────────────────────────────────────────────────┐
    │                    YOUR SONG  ♪ ♫                       │
    │           (WAV or MP3, ready to play)                   │
    └─────────────────────────────────────────────────────────┘
```

**The key idea:** Brain 1 (the Songwriter) is optional. You can give Brain 2 (the Studio Engineer) your own blueprint directly if you prefer full control. Or you can let Brain 1 handle the planning for you. It's your choice every time.

---

## What Can It Do?

ACE-Step has six creative modes. Think of them like different tools in a studio:

```
    ┌──────────────────────────────────────────────────────┐
    │                  YOUR CREATIVE TOOLKIT               │
    │                                                      │
    │  🎵 Text to Music    Describe it → Get a song        │
    │  🎨 Cover            Restyle an existing song        │
    │  🖌️ Repaint          Fix one section of a song       │
    │  🧱 Lego             Add layers to a backing track   │
    │  🔬 Extract          Pull out individual instruments │
    │  🎹 Complete         Add accompaniment to vocals     │
    └──────────────────────────────────────────────────────┘
```

### Text to Music — Start From Scratch

The simplest mode. Type a description, get a song.

**You write:** "melancholic indie folk with acoustic guitar and breathy female vocals"
**You get:** A complete song matching that description.

### Cover — Transform a Song's Style

Feed it an existing song and tell it what style you want instead. It keeps the structure (melody shape, rhythm, song form) but changes everything else.

**You provide:** A country ballad
**You write:** "heavy metal rock with distorted guitars and screaming vocals"
**You get:** The same song reimagined as heavy metal

### Repaint — Fix Just One Part

Generated a song you love, except the intro is weak? Repaint lets you regenerate just that section while keeping the rest untouched.

**You provide:** A song where seconds 0-10 need work
**You write:** "dramatic orchestral build-up"
**You get:** Same song, but with a new intro

### Lego — Stack Instrument Layers

Have a drum loop? Add bass. Have a guitar track? Add strings on top. Lego lets you build up a song one layer at a time.

### Extract — Pull Apart a Mix

The opposite of Lego. Give it a full mix and ask it to isolate just the vocals, or just the drums, or just the guitar.

### Complete — Add Accompaniment

Have a vocal recording with nothing else? Complete generates the backing instruments to match.

---

## What Do I Need to Run It?

### The Short Answer

A computer with a decent graphics card (GPU). The better the GPU, the faster and longer your songs can be.

### Hardware Guide

```
    YOUR GPU MEMORY          WHAT YOU CAN DO
    ─────────────────────────────────────────────────────

    4 GB  (entry level)      Songs up to 3 minutes
    ▓░░░░░░░░░░░░░░░░░░░    1 song at a time
                             Basic mode only (no Songwriter brain)

    8 GB  (mainstream)       Songs up to 6 minutes
    ▓▓▓▓░░░░░░░░░░░░░░░░    1-2 songs at a time
                             Optional lightweight Songwriter brain

    12 GB (sweet spot)       Songs up to 6 minutes
    ▓▓▓▓▓▓░░░░░░░░░░░░░░    2-4 songs at a time
                             Full Songwriter brain available

    16 GB (enthusiast)       Songs up to 8 minutes
    ▓▓▓▓▓▓▓▓░░░░░░░░░░░░    2-4 songs at a time
                             Larger, smarter Songwriter brain

    24 GB+ (high end)        Songs up to 10 minutes
    ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░    Up to 8 songs at a time
                             All features unlocked
```

**Common GPUs and where they land:**

| GPU | Memory | Tier |
|-----|--------|------|
| GTX 1050 Ti | 4 GB | Entry |
| RTX 3060 / 4060 | 8 GB | Mainstream |
| RTX 3070 / 4070 | 8-12 GB | Sweet spot |
| RTX 3080 / 4080 | 12-16 GB | Enthusiast |
| RTX 4090 | 24 GB | High end |
| Apple M1/M2/M3 (Mac) | Shared memory | Supported, varies |

**Disk space:** About 100 GB free. The AI models are large files (around 60 GB total) that download automatically the first time you run the software.

**Operating system:** Windows, Mac, or Linux all work.

---

## Getting It Running

### On Windows (Easiest Path)

1. Download the portable package from the ACE-Step website (a single .7z file)
2. Extract it (right-click → Extract with 7-Zip or WinRAR)
3. Double-click **start_gradio_ui.bat** inside the extracted folder
4. A browser window opens — that's your studio
5. On first launch, models download automatically (30 min to 2 hours depending on internet speed)

That's it. No programming required.

### On Mac or Linux

You'll need to type a few commands in the terminal, but it's straightforward:

```
Step 1:  Install the "uv" package manager (a one-time setup)
Step 2:  Download ACE-Step from GitHub
Step 3:  Run "uv sync" to install everything
Step 4:  Run "uv run acestep" to launch
Step 5:  Open your browser to http://localhost:7860
```

The project's README on GitHub walks through each step with copy-paste commands.

---

## The Interface: What You'll See

When ACE-Step opens in your browser, you get a web interface with three main areas:

```
    ┌─────────────────────────────────────────────────────────────┐
    │  ACE-Step 1.5                                               │
    ├─────────────┬───────────────────┬───────────────────────────┤
    │  Generate   │  LoRA Training    │  Dataset Explorer         │
    ├─────────────┴───────────────────┴───────────────────────────┤
    │                                                             │
    │  The Generate tab is where you'll spend 95% of your time.   │
    │                                                             │
    │  LoRA Training is for teaching the AI your personal style.  │
    │                                                             │
    │  Dataset Explorer is for browsing example prompts.          │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

### The Generate Tab

This is your main workspace. It has two modes:

**Simple Mode** — For when you want quick results
- Type a natural description like "a soft love song for a quiet evening"
- Click "Create Sample" and the AI fills in all the details
- Click "Generate Music" — done

**Custom Mode** — For when you want precise control
- You write the exact description (caption)
- You write the lyrics with structure tags
- You set the tempo, key, and duration
- You adjust advanced settings if you want

Most people start with Simple Mode, then move to Custom Mode once they understand how the system responds.

---

## Writing Prompts: Talking to the AI

The most important skill with ACE-Step is learning how to describe what you want. You communicate through two main inputs:

### The Caption — Your Overall Vision

The caption is a short paragraph describing the entire song's vibe. Think of it as the answer to: "If you walked into a studio with session musicians, how would you describe what you want?"

**Vague (the AI will guess a lot):**
> "a sad song"

**Better (gives the AI real direction):**
> "melancholic piano ballad with soft female vocals, gentle string accompaniment, slow tempo, intimate and heartbreaking atmosphere"

**Tips for good captions:**
- Name the genre: pop, rock, jazz, electronic, folk, hip-hop, lo-fi, synthwave
- Name the instruments: acoustic guitar, piano, synth pads, 808 drums, strings
- Name the mood: melancholic, uplifting, energetic, dreamy, aggressive, intimate
- Name the production style: lo-fi, polished, live recording, bedroom pop, orchestral

### The Lyrics — Your Song's Script

Lyrics do double duty in ACE-Step. They're not just words — they tell the AI how the song should be **structured** over time.

You use tags in square brackets to mark sections:

```
[Intro]

[Verse 1]
Walking through the empty streets
Thinking of your gentle touch
Summer nights and softer dreams

[Chorus]
We rise together
Into the light
This is our moment tonight

[Verse 2]
Stars are falling from the sky
Your hand fits perfectly in mine

[Bridge]
If tomorrow never comes
At least we had this

[Chorus]
We rise together
Into the light
This is our moment tonight

[Outro]
```

**What the tags do:**

```
    [Intro]          → Sets up atmosphere, usually instrumental
    [Verse]          → Main storytelling section, moderate energy
    [Pre-Chorus]     → Builds tension before the chorus
    [Chorus]         → Emotional peak, highest energy
    [Bridge]         → A shift — different melody, different feel
    [Instrumental]   → No vocals, just instruments
    [Outro]          → Winds down, often fades
```

**Lyric tips:**
- Keep lines around 6-10 syllables so the AI can fit them naturally
- Use UPPERCASE for words you want emphasized or shouted
- Use (parentheses) for background vocals or echoes
- Add descriptors to tags for extra guidance: `[Chorus - anthemic]` or `[Verse - whispered]`

### Optional: Metadata

You can also set specific musical parameters:

| Setting | What It Means | Typical Values |
|---------|---------------|----------------|
| **BPM** | Speed of the song | 60-80 (slow), 90-120 (medium), 130-180 (fast) |
| **Key** | Musical key | C Major (bright), A minor (melancholic), etc. |
| **Duration** | Song length in seconds | 60 (1 min), 180 (3 min), 300 (5 min) |
| **Language** | Vocal language | English, Spanish, Japanese, Chinese, 50+ others |

If you don't set these, the AI will choose sensible defaults based on your caption and lyrics.

---

## Working With Reference Audio

One of ACE-Step's most powerful features is using existing audio to guide generation. There are three ways to do this:

```
    ┌──────────────────────────────────────────────────────────┐
    │               THREE WAYS TO USE AUDIO INPUT              │
    │                                                          │
    │   1. REFERENCE AUDIO (style guide)                       │
    │      ┌──────────┐                                        │
    │      │ jazz.mp3 │──→ "Make something that SOUNDS         │
    │      └──────────┘     like this — same warmth, same      │
    │                       texture, same vibe"                │
    │                                                          │
    │   2. SOURCE AUDIO + COVER (restyle a song)               │
    │      ┌──────────┐                                        │
    │      │ song.mp3 │──→ "Keep the STRUCTURE of this song    │
    │      └──────────┘     but change the style completely"   │
    │                                                          │
    │   3. SOURCE AUDIO + REPAINT (fix a section)              │
    │      ┌──────────┐                                        │
    │      │ song.mp3 │──→ "Keep the whole song EXCEPT         │
    │      └──────────┘     regenerate seconds 10-20"          │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
```

### Cover Mode: The Style Transformer

This is the mode for turning one genre into another. The key control is **Audio Cover Strength** — a slider from 0 to 100%:

```
    Audio Cover Strength

    0%                     50%                    100%
    ├──────────────────────┼──────────────────────┤
    │                      │                      │
    Ignores the         Balanced              Follows the
    original audio.     blend.                original closely.
    Pure text-based     Recognizable          Same structure,
    generation.         but transformed.      subtle changes only.


    For dramatic genre changes (country → metal):  use 30-50%
    For moderate changes (pop → jazz):             use 50-70%
    For subtle changes (rock → indie rock):        use 70-90%
```

**Example: Country to Heavy Metal**

1. Upload your country song as source audio
2. Select the "Cover" task
3. Set Audio Cover Strength to about 40%
4. Write a caption like: *"heavy metal rock with heavily distorted electric guitars, aggressive double bass drumming, powerful screaming vocals, fast tempo, high energy, intense dark atmosphere"*
5. Generate a few variations (batch size 2-4)
6. Pick your favorite

---

## The Batch Generation Workflow

A critical concept: **you should almost never generate just one version.** AI music generation involves randomness. Think of it like rolling dice — sometimes you get exactly what you wanted, sometimes you don't. The solution is to roll several times and pick the best.

```
    THE RECOMMENDED WORKFLOW

    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │  Write your  │────▶│  Generate a  │────▶│  Listen to   │
    │  description │     │  batch of 4  │     │  all four    │
    └──────────────┘     └──────────────┘     └─────┬────────┘
                                                    │
                                ┌───────────────────┼──────────┐
                                │                   │          │
                                ▼                   ▼          ▼
                          ┌──────────┐       ┌──────────┐  ┌──────────┐
                          │ Love it? │       │ Close    │  │ Not      │
                          │ Export!  │       │ but not  │  │ right?   │
                          └──────────┘       │ quite?   │  │ Tweak    │
                                             │ Repaint  │  │ prompt   │
                                             │ the weak │  │ & retry  │
                                             │ section  │  └──────────┘
                                             └──────────┘
```

**AutoGen:** There's also an "auto-generate" feature that starts preparing the next batch while you're listening to the current one. This keeps your creative flow uninterrupted.

---

## Training Your Own Style (LoRA)

LoRA is a way to teach ACE-Step your personal sound. If you have a collection of songs that represent a style you want the AI to learn — your own recordings, a specific genre, a particular mood — you can train a custom "style adapter."

### What Is a LoRA?

Think of it as a small plug-in that sits on top of the base AI model:

```
    ┌──────────────────────────────────────┐
    │         BASE AI MODEL                │
    │   (knows how to make all kinds       │
    │    of music in general)              │
    │                                      │
    │    ┌──────────────────────────┐      │
    │    │    YOUR LoRA ADAPTER     │      │
    │    │  (teaches it YOUR style) │      │
    │    │                          │      │
    │    │  Trained on 8-20 of      │      │
    │    │  your reference songs    │      │
    │    └──────────────────────────┘      │
    │                                      │
    └──────────────────────────────────────┘

    Without LoRA: generic but versatile
    With LoRA:    sounds more like YOUR music
```

### How to Train One

1. **Collect 8-20 songs** that represent the style you want
2. Go to the **LoRA Training** tab in the interface
3. Point it at the folder with your audio files
4. Click "Scan" — it analyzes each file automatically
5. Review and edit the auto-generated labels if needed
6. Click "Start Training" — takes about 1 hour on a good GPU
7. When finished, you have a LoRA adapter file you can load any time

### Using Your LoRA

1. In the Generate tab, find the "LoRA Adapter" section
2. Enter the path to your trained LoRA
3. Click "Load LoRA"
4. Adjust the **LoRA Scale** slider:

```
    LoRA Scale

    0%                     50%                    100%
    ├──────────────────────┼──────────────────────┤
    │                      │                      │
    No LoRA effect.     Half strength.         Full LoRA effect.
    Pure base model.    Blended style.         Maximum influence
                                               from your training.
```

5. Generate music as usual — the output will now be influenced by your trained style

### Current Limitation: One LoRA at a Time

Today, you can only use one LoRA adapter at a time. Loading a new one replaces the previous one. You cannot stack multiple styles simultaneously (for example, "jazz LoRA at 60% + vocal LoRA at 40%"). This is a known limitation that may be addressed in a future update.

---

## The Speed Question

How long does generation take? It depends on your hardware and settings:

```
    GENERATION SPEED (approximate)

    GPU Tier          30-sec song    2-min song     5-min song
    ──────────────────────────────────────────────────────────
    Entry (4 GB)      10-15 sec      20-30 sec      N/A
    Mainstream (8 GB)  5-10 sec      10-18 sec      15-25 sec
    Sweet spot (12 GB) 3-8 sec        8-12 sec      10-15 sec
    High end (24 GB)   1-3 sec        3-7 sec        5-10 sec
```

**Fast Mode vs. Quality Mode:**
- **Turbo** (default): 8 processing steps, very fast, good quality
- **SFT/Base**: 50 processing steps, slower, more detail and nuance

Most people use Turbo for day-to-day work and switch to SFT/Base for final versions.

---

## Languages

ACE-Step can generate vocals in 50+ languages, including:

English, Spanish, French, German, Italian, Portuguese, Chinese (Mandarin & Cantonese), Japanese, Korean, Hindi, Bengali, Arabic, Turkish, Thai, Vietnamese, Swedish, Dutch, Polish, Hebrew, and many more.

To use a different language:
1. Select the vocal language in the interface
2. Write your lyrics in that language
3. The AI generates vocals with appropriate pronunciation and style

You can even mix languages within a single song.

---

## Tips From Experience

### Start Simple, Then Refine
Don't try to control everything on your first attempt. Start with a short caption and see what the AI gives you. Then add detail in areas where the output surprised you.

### Generate in Batches
Always generate 2-4 versions at once. Picking the best from several options is faster and more satisfying than trying to get one perfect result.

### Fix, Don't Redo
If 90% of a song is great but one section is off, use **Repaint** to regenerate just that section. Don't throw away the whole thing.

### Be Specific About Instruments
"rock song" gives the AI too much freedom. "rock song with crunchy rhythm guitar, punchy snare, and gravelly male vocals" tells it exactly what you're hearing in your head.

### Use Structure Tags in Lyrics
Even if you don't care about the actual words yet, writing `[Intro] [Verse] [Chorus] [Verse] [Chorus] [Bridge] [Chorus] [Outro]` gives the AI a roadmap for energy and dynamics.

### Try Different Seeds
Every generation uses a random "seed" number. If you like your settings but want to hear different interpretations, just click generate again — each run uses a new seed automatically. You can also set a specific seed number to reproduce a result you liked.

### The Songwriter Brain Is Optional
If you already know exactly what you want (tempo, key, structure, instruments), you can turn off "Thinking Mode" to skip Brain 1 entirely. This makes generation faster and gives you more direct control.

---

## What ACE-Step Is Not

It's worth being clear about what this tool isn't:

- **It's not a DAW.** It doesn't replace Ableton, Logic, or FL Studio. It generates raw audio that you can import into your DAW for further editing.
- **It's not perfect every time.** Expect to generate several versions and pick the best. Think of it as a creative collaborator, not a jukebox.
- **It's not a cloud service.** It runs on your machine. If your GPU is small, results will be limited. There's no server doing the work for you.
- **It's not one-click magic.** The best results come from learning how to describe what you want. That's a skill that improves with practice.

What it *is*: a powerful, free, open instrument that puts AI music generation in your hands — literally on your own hardware — with full creative control and ownership.

---

## Quick Reference Card

```
    ┌─────────────────────────────────────────────────────────┐
    │                    QUICK REFERENCE                      │
    │                                                         │
    │  GENERATE A SONG                                        │
    │    Caption:  Describe style, instruments, mood          │
    │    Lyrics:   [Verse] [Chorus] [Bridge] with words       │
    │    Click:    Generate Music                             │
    │                                                         │
    │  RESTYLE A SONG (Cover)                                 │
    │    Upload:   Source audio                               │
    │    Task:     Cover                                      │
    │    Caption:  Describe the NEW style                     │
    │    Strength: 30-50% for big changes, 70-90% for subtle  │
    │                                                         │
    │  FIX A SECTION (Repaint)                                │
    │    Upload:   Source audio                               │
    │    Task:     Repaint                                    │
    │    Time:     Set start and end (in seconds)             │
    │    Caption:  Describe what the fixed section should be  │
    │                                                         │
    │  APPLY CUSTOM STYLE (LoRA)                              │
    │    Load:     Your trained LoRA adapter file             │
    │    Scale:    0-100% (how much style influence)          │
    │    Then:     Generate as usual                          │
    │                                                         │
    │  KEYBOARD SHORTCUTS                                     │
    │    Batch size 2-4 recommended for every generation      │
    │    Use Turbo mode for speed, SFT/Base for quality       │
    │    Turn off Thinking Mode if you know exactly what      │
    │    you want                                             │
    └─────────────────────────────────────────────────────────┘
```
