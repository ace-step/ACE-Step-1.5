# ACE-Step 1.5 Ultimate Guide (Must Read)

**Language / 语言 / 言語:** [English](Tutorial.md) | [中文](../zh/Tutorial.md) | [日本語](../ja/Tutorial.md)

---

Hello everyone, I'm Gong Junmin, the developer of ACE-Step. Through this tutorial, I'll guide you through the design philosophy and usage of ACE-Step 1.5.

## Mental Models

Before we begin, we need to establish the correct mental models to set proper expectations.

### Human-Centered Design

This model is not designed for **one-click generation**, but for **human-centered generation**.

Understanding this distinction is crucial.

### What is One-Click Generation?

You input a prompt, click generate, listen to a few versions, pick one that sounds good, and use it. If someone else inputs the same prompt, they'll likely get similar results.

In this mode, you and AI have a **client-vendor** relationship. You come with a clear purpose, with a vague expectation in mind, hoping AI delivers a product close to that expectation. Essentially, it's not much different from searching on Google or finding songs on Spotify—just with a bit more customization.

AI is a service, not a creative inspirer.

Suno, Udio, MiniMax, Mureka—these platforms are all designed with this philosophy. They can scale up models as services to ensure delivery. Your generated music is bound by their agreements; you can't run it locally, can't fine-tune for personalized exploration; if they secretly change models or terms, you can only accept it.

### What is Human-Centered Generation?

If we weaken the AI layer and strengthen the human layer—letting more human will, creativity, and inspiration give life to AI—this is human-centered generation.

Unlike the strong purposefulness of one-click generation, human-centered generation has more of a **playful** nature. It's more like an interactive game where you and the model are **collaborators**.

The workflow is like this: you throw out some inspiration seeds, get a few songs, choose interesting directions from them to continue iterating—
- Adjust prompts to regenerate
- Use **Cover** to maintain structure and adjust details
- Use **Repaint** for local modifications
- Use **Add Layer** to add or remove instrument layers

At this point, AI is not a servant to you, but an **inspirer**.

### What Conditions Must This Design Meet?

For human-centered generation to truly work, the model must meet several key conditions:

**First, it must be open-source, locally runnable, and trainable.**

This isn't technical purism, but a matter of ownership. When you use closed-source platforms, you don't own the model, and your generated works are bound by their agreements. Version updates, term changes, service shutdowns—none of these are under your control.

But when the model is open-source and locally runnable, everything changes: **You forever own this model, and you forever own all the creations you make with it.** No third-party agreement hassles, no platform risks, you can fine-tune, modify, and build your own creative system based on it. Your works will forever belong to you. It's like buying an instrument—you can use it anytime, anywhere, and adjust it anytime, anywhere.

**Second, it must be fast.**

Human time is precious, but more importantly—**slow generation breaks flow state**.

The core of human-centered workflow is the rapid cycle of "try, listen, adjust." If each generation takes minutes, your inspiration dissipates while waiting, and the "play" experience degrades into the "wait" ordeal.

Therefore, we specifically optimized ACE-Step for this: while ensuring quality, we made generation fast enough to support a smooth human-machine dialogue rhythm.

### Finite Game vs Infinite Game

One-click generation is a **finite game**—clear goals, result-oriented, ends at the finish line. To some extent, it coldly hollows out the music industry, replacing many people's jobs.

Human-centered generation is an **infinite game**—because the fun lies in the process, and the process never ends.

Our vision is to democratize AI music generation. Let ACE-Step become a big toy in your pocket, let music return to **Play** itself—the creative "play," not just clicking play.

---

## The Elephant Rider Metaphor

> Recommended reading: [The Complete Guide to Mastering Suno](https://www.notion.so/The-Complete-Guide-to-Mastering-Suno-Advanced-Strategies-for-Professional-Music-Generation-2d6ae744ebdf8024be42f6645f884221)—this blog tutorial can help you establish the foundational understanding of AI music.

AI music generation is like the famous **elephant rider metaphor** in psychology.

Consciousness rides on the subconscious, humans ride on elephants. You can give directions, but you can't make the elephant precisely and instantly execute every command. It has its own inertia, its own temperament, its own will.

This elephant is the music generation model.

### The Iceberg Model

Between audio and semantics lies a hidden iceberg.

What we can describe with language—style, instruments, timbre, emotion, scenes, progression, lyrics, vocal style—these are familiar words, the parts we can touch. But together, they're still just a tiny tip of the audio iceberg above the water.

What's the most precise control? You input the expected audio, and the model returns it unchanged.

But as long as you're using text descriptions, references, prompts—the model will have room to play. This isn't a bug, it's the nature of things.

### What is the Elephant?

This elephant is a fusion of countless elements: data distribution, model scale, algorithm design, annotation bias, evaluation bias—**it's an abstract crystallization of human music history and engineering trade-offs.**

Any deviation in these elements will cause it to fail to accurately reflect your taste and expectations.

Of course, we can expand data scale, improve algorithm efficiency, increase annotation precision, expand model capacity, introduce more professional evaluation systems—these are all directions we can optimize as model developers.

But even if one day we achieve technical "perfection," there's still a fundamental problem we can't avoid: **taste.**

### Taste and Expectations

Taste varies from person to person.

If a music generation model tries to please all listeners, its output will tend toward the popular average of human music history—**this will be extremely mediocre.**

It's humans who give sound meaning, emotion, experience, life, and cultural symbolic value. It's a small group of artists who create unique tastes, then drive ordinary people to consume and follow, turning niche into mainstream popularity. These pioneering minority artists become legends.

So when you find the model's output "not to your taste," this might not be the model's problem—**but rather your taste happens to be outside that "average."** This is a good thing.

This means: **You need to learn to guide this elephant, not expect it to automatically understand you.**

---

## Knowing the Elephant Herd: Model Architecture and Selection

Now you understand the "elephant" metaphor. But actually—

**This isn't one elephant, but an entire herd—elephants large and small, forming a family.** 🐘🐘🐘🐘

### Architecture Principles: Two Brains

ACE-Step 1.5 uses a **hybrid architecture** with two core components working together:

```
User Input → [5Hz LM] → Semantic Blueprint → [DiT] → Audio
              ↓
         Metadata Inference
         Caption Optimization
         Structure Planning
```

**5Hz LM (Language Model) — Planner (Optional)**

The LM is an "omni-capable planner" responsible for understanding your intent and making plans:
- Infers music metadata (BPM, key, duration, etc.) through **Chain-of-Thought**
- Optimizes and expands your caption—understanding and supplementing your intent
- Generates **semantic codes**—implicitly containing composition melody, orchestration, and some timbre information

The LM learns **world knowledge** from training data. It's a planner that improves usability and helps you quickly generate prototypes.

**But the LM is not required.**

If you're very clear about what you want, or already have a clear planning goal—you can completely skip the LM planning step by not using `thinking` mode.

For example, in **Cover mode**, you use reference audio to constrain composition, chords, and structure, letting DiT generate directly. Here, **you replace the LM's work**—you become the planner yourself.

Another example: in **Repaint mode**, you use reference audio as context, constraining timbre, mixing, and details, letting DiT directly adjust locally. Here, DiT is more like your creative brainstorming partner, helping with creative ideation and fixing local disharmony.

**DiT (Diffusion Transformer) — Executor**

DiT is the "audio craftsman," responsible for turning plans into reality:
- Receives semantic codes and conditions generated by LM
- Gradually "carves" audio from noise through the **diffusion process**
- Decides final timbre, mixing, details

**Why this design?**

Traditional methods let diffusion models generate audio directly from text, but text-to-audio mapping is too vague. ACE-Step introduces LM as an intermediate layer:
- LM excels at understanding semantics and planning
- DiT excels at generating high-fidelity audio
- They work together, each doing their part

### Choosing the Planner: LM Models

LM has four options: **No LM** (disable thinking mode), **0.6B**, **1.7B**, **4B**.

Their training data is completely identical; the difference is purely in **knowledge capacity**:
- Larger models have richer world knowledge
- Larger models have stronger memory (e.g., remembering reference audio melodies)
- Larger models perform relatively better on long-tail styles or instruments

| Choice | Speed | World Knowledge | Memory | Use Cases |
|--------|:-----:|:---------------:|:------:|-----------|
| No LM | ⚡⚡⚡⚡ | — | — | You do the planning (e.g., Cover mode) |
| `0.6B` | ⚡⚡⚡ | Basic | Weak | Low VRAM (< 8GB), rapid prototyping |
| `1.7B` | ⚡⚡ | Medium | Medium | **Default recommendation** |
| `4B` | ⚡ | Rich | Strong | Complex tasks, high-quality generation |

**How to choose?**

Based on your hardware:
- **VRAM < 8GB** → No LM or `0.6B`
- **VRAM 8–16GB** → `1.7B` (default)
- **VRAM > 16GB** → `1.7B` or `4B`

### Choosing the Executor: DiT Models

With a planning scheme, you still need to choose an executor. DiT is the core of ACE-Step 1.5—it handles various tasks and decides how to interpret LM-generated codes.

We've open-sourced **4 Turbo models**, **1 SFT model**, and **1 Base model** — plus their **XL (4B)** counterparts for higher audio quality.

#### Turbo Series (Recommended for Daily Use)

Turbo models are trained with distillation, generating high-quality audio in just 8 steps. The core difference between the four variants is the **shift hyperparameter configuration during distillation**.

**What is shift?**

Shift determines the "attention allocation" during DiT denoising:
- **Larger shift** → More effort spent on early denoising (building large structure from pure noise), **stronger semantics**, clearer overall framework
- **Smaller shift** → More even step distribution, **more details**, but details might also be noise

Simple understanding: high shift is like "draw outline first then fill details," low shift is like "draw and fix simultaneously."

| Model | Distillation Config | Characteristics |
|-------|---------------------|-----------------|
| `turbo` (default) | Joint distillation on shift 1, 2, 3 | **Best balance of creativity and semantics**, thoroughly tested, recommended first choice |
| `turbo-shift1` | Distilled only on shift=1 | Richer details, but semantics weaker |
| `turbo-shift3` | Distilled only on shift=3 | Clearer, richer timbre, but may sound "dry," minimal orchestration |
| `turbo-continuous` | Experimental, supports continuous shift 1–5 | Most flexible tuning, but not thoroughly tested |

You can choose based on target music style—you might find you prefer a certain variant. **We recommend starting with default turbo**—it's the most balanced and proven choice.

#### SFT Model

Compared to Turbo, SFT model has two notable features:
- **Supports CFG** (Classifier-Free Guidance), allowing fine-tuning of prompt adherence
- **More steps** (50 steps), giving the model more time to "think"

The cost: more steps mean error accumulation, audio clarity may be slightly inferior to Turbo. But its **detail expression and semantic parsing will be better**.

If you don't care about inference time, like tuning CFG and steps, and prefer that rich detail feel—SFT is a good choice. LM-generated codes can also work with SFT models.

#### Base Model

Base is the **master of all tasks**, with three exclusive tasks beyond SFT and Turbo:

| Task | Description |
|------|-------------|
| `extract` | Extract single tracks from mixed audio (e.g., separate vocals) |
| `lego` | Add new tracks to existing tracks (e.g., add drums to guitar) |
| `complete` | Add mixed accompaniment to single track (e.g., add guitar+drums accompaniment to vocals) |

Additionally, Base has the **strongest plasticity**. If you have large-scale fine-tuning needs, we recommend starting experiments with Base to train your own SFT model.

#### Creating Your Custom Model

Beyond official models, you can also use **LoRA fine-tuning** to create your custom model.

We'll release an example LoRA model—trained on 20+ "Happy New Year" themed songs, specifically suited for expressing festive atmosphere. This is just a starting point.

**What does a custom model mean?**

You can reshape DiT's capabilities and preferences with your own data recipe:
- Like a specific timbre style? Train with that type of songs
- Want the model better at a certain genre? Collect related data for fine-tuning
- Have your own unique aesthetic taste? "Teach" it to the model

This greatly expands **customization and playability**—train a model unique to you with your aesthetic taste.

> For the detailed LoRA training guide, see the [LoRA Training Tutorial](./LoRA_Training_Tutorial.md). You can also use the "LoRA Training" tab in Gradio UI for one-click training.

#### XL (4B) Models

XL models use a larger 4B-parameter DiT decoder for higher audio quality. They come in the same three variants (base, sft, turbo) and behave identically — just with better generation quality. **All LM models (0.6B / 1.7B / 4B) are fully compatible with XL.**

**Requirements:** XL models need ~9GB VRAM for weights (vs ~4.7GB for 2B). Minimum 12GB VRAM with offload + quantization, 20GB+ recommended.

| XL Model (full name) | Steps | CFG | VRAM | Notes |
|----------------------|:-----:|:---:|:----:|-------|
| `acestep-v15-xl-turbo` | 8 | ❌ | ≥12GB | Fast + high quality, best daily driver on 20GB+ GPUs |
| `acestep-v15-xl-sft` | 50 | ✅ | ≥12GB | Highest quality, tunable CFG |
| `acestep-v15-xl-base` | 50 | ✅ | ≥12GB | All tasks including extract/lego/complete |

#### DiT Selection Summary

| Model | Steps | CFG | Speed | Exclusive Tasks | Recommended Scenarios |
|-------|:-----:|:---:|:-----:|-----------------|----------------------|
| `turbo` (default) | 8 | ❌ | ⚡⚡⚡ | — | Daily use, rapid iteration |
| `sft` | 50 | ✅ | ⚡ | — | Pursuing details, like tuning |
| `base` | 50 | ✅ | ⚡ | extract, lego, complete | Special tasks, large-scale fine-tuning |
| **`acestep-v15-xl-turbo`** | 8 | ❌ | ⚡⚡ | — | Best daily driver on 20GB+ GPUs |
| **`acestep-v15-xl-sft`** | 50 | ✅ | ⚡ | — | Highest quality, ≥12GB VRAM |
| **`acestep-v15-xl-base`** | 50 | ✅ | ⚡ | extract, lego, complete | All tasks with higher quality, ≥12GB VRAM |

### Combination Strategies

Default configuration is **turbo + 1.7B LM**, suitable for most scenarios.

| Need | Recommended Combination |
|------|------------------------|
| Fastest speed | `turbo` + No LM or `0.6B` |
| Daily use | `turbo` + `1.7B` (default) |
| Pursuing details | `sft` + `1.7B` or `4B` |
| Special tasks | `base` |
| Large-scale fine-tuning | `base` |
| Low VRAM (< 4GB) | `turbo` + No LM + CPU offload |

### Downloading Models

```bash
# Download default models (turbo + 1.7B LM)
uv run acestep-download

# Download all models
uv run acestep-download --all

# Download specific model
uv run acestep-download --model acestep-v15-base
uv run acestep-download --model acestep-5Hz-lm-0.6B

# List available models
uv run acestep-download --list
```

You need to download models into a `checkpoints` folder for easy identification.

---

## Guiding the Elephant: What Can You Control?

Now that you know this herd of elephants, let's learn how to communicate with them.

Each generation is determined by three types of factors: **input control**, **inference hyperparameters**, and **random factors**.

### I. Input Control: What Do You Want?

This is the part where you communicate "creative intent" with the model—what kind of music you want to generate.

| Category | Parameter | Function |
|----------|-----------|----------|
| **Task Type** | `task_type` | Determines generation mode: text2music, cover, repaint, lego, extract, complete |
| **Text Input** | `caption` | Description of overall music elements: style, instruments, emotion, atmosphere, timbre, vocal gender, progression, etc. |
| | `lyrics` | Temporal element description: lyric content, music structure evolution, vocal changes, vocal/instrument performance style, start/end style, articulation, etc. (use `[Instrumental]` for instrumental music) |
| **Music Metadata** | `bpm` | Tempo (30–300) |
| | `keyscale` | Key (e.g., C Major, Am) |
| | `timesignature` | Time signature (4/4, 3/4, 6/8) |
| | `vocal_language` | Vocal language |
| | `duration` | Target duration (seconds) |
| **Audio Reference** | `reference_audio` | Global reference for timbre or style (for cover, style transfer) |
| | `src_audio` | Source audio for non-text2music tasks (text2music defaults to silence, no input needed) |
| | `audio_codes` | Semantic codes input to model in Cover mode (advanced: reuse codes for variants, convert songs to codes for extension, combine like DJ mixing) |
| **Interval Control** | `repainting_start/end` | Time interval for operations (repaint redraw area / lego new track area) |

---

#### About Caption: The Most Important Input

**Caption is the most important factor affecting generated music.**

It supports multiple input formats: simple style words, comma-separated tags, complex natural language descriptions. We've trained to be compatible with various formats, ensuring text format doesn't significantly affect model performance.

**We provide at least 5 ways to help you write good captions:**

1. **Random Dice** — Click the random button in the UI to see how example captions are written. You can use this standardized caption as a template and have an LLM rewrite it to your desired form.

2. **Format Auto-Rewrite** — We support using the `format` feature to automatically expand your handwritten simple caption into complex descriptions.

3. **CoT Rewrite** — If LM is initialized, whether `thinking` mode is enabled or not, we support rewriting and expanding captions through Chain-of-Thought (unless you actively disable it in settings, or LM is not initialized).

4. **Audio to Caption** — Our LM supports converting your input audio to caption. While precision is limited, the vague direction is correct—enough as a starting point.

5. **Simple Mode** — Just input a simple song description, and LM will automatically generate complete caption, lyrics, and metas samples—suitable for quick starts.

Regardless of which method, they all solve a real problem: **As ordinary people, our music vocabulary is impoverished.**

If you want generated music to be more interesting and meet expectations, **Prompting is always the optimal option**—it brings the highest marginal returns and surprises.

**Common Dimensions for Caption Writing:**

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

**Some Practical Principles:**

1. **Specific beats vague** — "sad piano ballad with female breathy vocal" works better than "a sad song."

2. **Combine multiple dimensions** — Single-dimension descriptions give the model too much room to play; combining style+emotion+instruments+timbre can more precisely anchor your desired direction.

3. **Use references well** — "in the style of 80s synthwave" or "reminiscent of Bon Iver" can quickly convey complex aesthetic preferences.

4. **Texture words are useful** — Adjectives like warm, crisp, airy, punchy can influence mixing and timbre tendencies.

5. **Don't pursue perfect descriptions** — Caption is a starting point, not an endpoint. Write a general direction first, then iterate based on results.

6. **Description granularity determines freedom** — More omitted descriptions give the model more room to play, more random factor influence; more detailed descriptions constrain the model more. Decide specificity based on your needs—want surprises? Write less. Want control? Write more details.

7. **Avoid conflicting words** — Conflicting style combinations easily lead to degraded output. For example, wanting both "classical strings" and "hardcore metal" simultaneously—the model will try to fuse but usually not ideal. Especially when `thinking` mode is enabled, LM has weaker caption generalization than DiT. When prompting is unreasonable, the chance of pleasant surprises is smaller.

   **Ways to resolve conflicts:**
   - **Repetition reinforcement** — Strengthen the elements you want more in mixed styles by repeating certain words
   - **Conflict to evolution** — Transform style conflicts into temporal style evolution. For example: "Start with soft strings, middle becomes noisy dynamic metal rock, end turns to hip-hop"—this gives the model clear guidance on how to handle different styles, rather than mixing them into a mess

> For more prompting tips, see: [The Complete Guide to Mastering Suno](https://www.notion.so/The-Complete-Guide-to-Mastering-Suno-Advanced-Strategies-for-Professional-Music-Generation-2d6ae744ebdf8024be42f6645f884221)—although it's a Suno tutorial, prompting ideas are universal.

---

#### About Lyrics: The Temporal Script

If Caption describes the music's "overall portrait"—style, atmosphere, timbre—then **Lyrics is the music's "temporal script"**, controlling how music unfolds over time.

Lyrics is not just lyric content. It carries:
- The lyric text itself
- **Structure tags** ([Verse], [Chorus], [Bridge]...)
- **Vocal style hints** ([raspy vocal], [whispered]...)
- **Instrumental sections** ([guitar solo], [drum break]...)
- **Energy changes** ([building energy], [explosive drop]...)

**Structure Tags are Key**

Structure tags (Meta Tags) are the most powerful tool in Lyrics. They tell the model: "What is this section, how should it be performed?"

**Common Structure Tags:**

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
| **Instrumental Sections** | `[Instrumental]` | Pure instrumental, no vocals |
| | `[Guitar Solo]` | Guitar solo |
| | `[Piano Interlude]` | Piano interlude |
| **Special Tags** | `[Fade Out]` | Fade out ending |
| | `[Silence]` | Silence |

**Combining Tags: Use Moderately**

Structure tags can be combined with `-` for finer control:

```
[Chorus - anthemic]
This is the chorus lyrics
Dreams are burning

[Bridge - whispered]
Whisper those words softly
```

This works better than writing `[Chorus]` alone—you're telling the model both what this section is (Chorus) and how to sing it (anthemic).

**⚠️ Note: Don't stack too many tags.**

```
❌ Not recommended:
[Chorus - anthemic - stacked harmonies - high energy - powerful - epic]

✅ Recommended:
[Chorus - anthemic]
```

Stacking too many tags has two risks:
1. The model might mistake tag content as lyrics to sing
2. Too many instructions confuse the model, making effects worse

**Principle**: Keep structure tags concise; put complex style descriptions in Caption.

**⚠️ Key: Maintain Consistency Between Caption and Lyrics**

**Models are not good at resolving conflicts.** If descriptions in Caption and Lyrics contradict, the model gets confused and output quality decreases.

```
❌ Conflict example:
Caption: "violin solo, classical, intimate chamber music"
Lyrics: [Guitar Solo - electric - distorted]

✅ Consistent example:
Caption: "violin solo, classical, intimate chamber music"
Lyrics: [Violin Solo - expressive]
```

**Checklist:**
- Instruments in Caption ↔ Instrumental section tags in Lyrics
- Emotion in Caption ↔ Energy tags in Lyrics
- Vocal description in Caption ↔ Vocal control tags in Lyrics

Think of Caption as "overall setting" and Lyrics as "shot script"—they should tell the same story.

**Vocal Control Tags:**

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

**Energy and Emotion Tags:**

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

**Lyric Text Writing Tips**

**1. Control Syllable Count**

**6-10 syllables per line** usually works best. The model aligns syllables to beats—if one line has 6 syllables and the next has 14, rhythm becomes strange.

```
❌ Bad example:
我站在窗前看着外面的世界一切都在改变（18 syllables）
你好（2 syllables）

✅ Good example:
我站在窗前（5 syllables）
看着外面世界（6 syllables）
一切都在改变（6 syllables）
```

**Tip**: Keep similar syllable counts for lines in the same position (e.g., first line of each verse) (±1-2 deviation).

**2. Use Case to Control Intensity**

Uppercase indicates stronger vocal intensity:

```
[Verse]
walking through the empty streets (normal intensity)

[Chorus]
WE ARE THE CHAMPIONS! (high intensity, shouting)
```

**3. Use Parentheses for Background Vocals**

```
[Chorus]
We rise together (together)
Into the light (into the light)
```

Content in parentheses is processed as background vocals or harmonies.

**4. Extend Vowels**

You can extend sounds by repeating vowels:

```
Feeeling so aliiive
```

But use cautiously—effects are unstable, sometimes ignored or mispronounced.

**5. Clear Section Separation**

Separate each section with blank lines:

```
[Verse 1]
First verse lyrics
Continue first verse

[Chorus]
Chorus lyrics
Chorus continues
```

**Avoiding "AI-flavored" Lyrics**

These characteristics make lyrics seem mechanical and lack human touch:

| Red Flag 🚩 | Description |
|-------------|-------------|
| **Adjective stacking** | "neon skies, electric hearts, endless dreams"—filling a section with vague imagery |
| **Rhyme chaos** | Inconsistent rhyme patterns, or forced rhymes causing semantic breaks |
| **Blurred section boundaries** | Lyric content crosses structure tags, Verse content "flows" into Chorus |
| **No breathing room** | Each line too long, can't sing in one breath |
| **Mixed metaphors** | First verse uses water imagery, second suddenly becomes fire, third is flying—listeners can't anchor |

**Metaphor discipline**: Stick to one core metaphor per song, exploring its multiple aspects. For example, choosing "water" as metaphor, you can explore: how love flows around obstacles like water, can be gentle rain or flood, reflects the other's image, can't be grasped but exists. One image, multiple facets—this gives lyrics cohesion.

**Writing Instrumental Music**

If generating pure instrumental music without vocals:

```
[Instrumental]
```

Or use structure tags to describe instrumental development:

```
[Intro - ambient]

[Main Theme - piano]

[Climax - powerful]

[Outro - fade out]
```

**Complete Example**

Assuming Caption is: `female vocal, piano ballad, emotional, intimate atmosphere, strings, building to powerful chorus`

```
[Intro - piano]

[Verse 1]
月光洒在窗台上
我听见你的呼吸
城市在远处沉睡
只有我们还醒着

[Pre-Chorus]
这一刻如此安静
却藏着汹涌的心

[Chorus - powerful]
让我们燃烧吧
像夜空中的烟火
短暂却绚烂
这就是我们的时刻

[Verse 2]
时间在指尖流过
我们抓不住什么
但至少此刻拥有
彼此眼中的火焰

[Bridge - whispered]
如果明天一切消散
至少我们曾经闪耀

[Final Chorus]
让我们燃烧吧
像夜空中的烟火
短暂却绚烂
THIS IS OUR MOMENT!

[Outro - fade out]
```

Note: In this example, Lyrics tags (piano, powerful, whispered) are consistent with Caption descriptions (piano ballad, building to powerful chorus, intimate), with no conflicts.

---

#### About Music Metadata: Optional Fine Control

**Most of the time, you don't need to manually set metadata.**

When you enable `thinking` mode (or enable `use_cot_metas`), LM automatically infers appropriate BPM, key, time signature, etc. based on your Caption and Lyrics. This is usually good enough.

But if you have clear ideas, you can also manually control them:

| Parameter | Control Range | Description |
|-----------|--------------|-------------|
| `bpm` | 30–300 | Tempo. Common distribution: slow songs 60–80, mid-tempo 90–120, fast songs 130–180 |
| `keyscale` | Key | e.g., `C Major`, `Am`, `F# Minor`. Affects overall pitch and emotional color |
| `timesignature` | Time signature | `4/4` (most common), `3/4` (waltz), `6/8` (swing feel) |
| `vocal_language` | Language | Vocal language. LM usually auto-detects from lyrics |
| `duration` | Seconds | Target duration. Actual generation may vary slightly |

**Understanding Control Boundaries**

These parameters are **guidance** rather than **precise commands**:

- **BPM**: Common range (60–180) works well; extreme values (like 30 or 280) have less training data, may be unstable
- **Key**: Common keys (C, G, D, Am, Em) are stable; rare keys may be ignored or shifted
- **Time signature**: `4/4` is most reliable; `3/4`, `6/8` usually OK; complex signatures (like `5/4`, `7/8`) are advanced, effects vary by style
- **Duration**: Short songs (30–60s) and medium length (2–4min) are stable; very long generation may have repetition or structure issues

**The Model's "Reference" Approach**

The model doesn't mechanically execute `bpm=120`, but rather:
1. Uses `120 BPM` as an **anchor point**
2. Samples from distribution near this anchor
3. Final result might be 118 or 122, not exactly 120

It's like telling a musician "around 120 tempo"—they'll naturally play in this range, not rigidly follow a metronome.

**When Do You Need Manual Settings?**

| Scenario | Suggestion |
|----------|------------|
| Daily generation | Don't worry, let LM auto-infer |
| Clear tempo requirement | Manually set `bpm` |
| Specific style (e.g., waltz) | Manually set `timesignature=3/4` |
| Need to match other material | Manually set `bpm` and `duration` |
| Pursue specific key color | Manually set `keyscale` |

**Tip**: If you manually set metadata but generation results clearly don't match—check if there's conflict with Caption/Lyrics. For example, Caption says "slow ballad" but `bpm=160`, the model gets confused.

**Recommended Practice**: Don't write tempo, BPM, key, and other metadata information in Caption. These should be set through dedicated metadata parameters (`bpm`, `keyscale`, `timesignature`, etc.), not described in Caption. Caption should focus on style, emotion, instruments, timbre, and other musical characteristics, while metadata information is handled by corresponding parameters.

---

#### About Audio Control: Controlling Sound with Sound

**Text is dimensionally reduced abstraction; the best control is still controlling with audio.**

There are three ways to control generation with audio, each with different control ranges and uses:

---

##### 1. Reference Audio: Global Acoustic Feature Control

Reference audio (`reference_audio`) is used to control the **acoustic features** of generated music—timbre, mixing style, performance style, etc. It **averages temporal dimension information** and acts **globally**.

**What Does Reference Audio Control?**

Reference audio mainly controls the **acoustic features** of generated music, including:
- **Timbre texture**: Vocal timbre, instrument timbre
- **Mixing style**: Spatial sense, dynamic range, frequency distribution
- **Performance style**: Vocal techniques, playing techniques, expression
- **Overall atmosphere**: The "feeling" conveyed through reference audio

**How Does the Backend Process Reference Audio?**

When you provide reference audio, the system performs the following processing:

1. **Audio Preprocessing**:
   - Load audio file, normalize to **stereo 48kHz** format
   - Detect silence, ignore if audio is completely silent
   - If audio length is less than 30 seconds, repeat to fill to at least 30 seconds
   - Randomly select 10-second segments from front, middle, and back positions, concatenate into 30-second reference segment

2. **Encoding Conversion**:
   - Use **VAE (Variational Autoencoder)** `tiled_encode` method to encode audio into **latent representation (latents)**
   - These latents contain acoustic feature information but remove specific melody, rhythm, and other structural information
   - Encoded latents are input as conditions to DiT generation process, **averaging temporal dimension information, acting globally on entire generation process**

---

##### 2. Source Audio: Semantic Structure Control

Source audio (`src_audio`) is used for **Cover tasks**, performing **melodic structure control**. Its principle is to quantize your input source audio into semantically structured information.

**What Does Source Audio Control?**

Source audio is converted into **semantically structured information**, including:
- **Melody**: Note direction and pitch
- **Rhythm**: Beat, accent, groove
- **Chords**: Harmonic progression and changes
- **Orchestration**: Instrument arrangement and layers
- **Some timbre**: Partial timbre information

**What Can You Do With It?**

1. **Control style**: Maintain source audio structure, change style and details
2. **Transfer style**: Apply source audio structure to different styles
3. **Retake lottery**: Generate similar structure but different variants, get different interpretations through multiple generations
4. **Control influence degree**: Control source audio influence strength through `audio_cover_strength` parameter (0.0–1.0)
   - Higher strength: generation results more strictly follow source audio structure
   - Lower strength: generation results have more room for free play

**Advanced Cover Usage**

You can use Cover to **Remix a song**, and it supports changing Caption and Lyrics:

- **Remix creation**: Input a song as source audio, reinterpret it by modifying Caption and Lyrics
  - Change style: Use different Caption descriptions (e.g., change from pop to rock)
  - Change lyrics: Rewrite lyrics with new Lyrics, maintaining original melody structure
  - Change emotion: Adjust overall atmosphere through Caption (e.g., change from sad to joyful)

- **Build complex music structures**: Build complex melodic direction, layers, and groove based on your needed structure influence degree
  - Fine-tune structure adherence through `audio_cover_strength`
  - Combine Caption and Lyrics modifications to create new expression while maintaining core structure
  - Can generate multiple versions, each with different emphasis on structure, style, lyrics

---

##### 3. Source Audio Context-Based Control: Local Completion and Modification

This is the **Repaint task**, performing completion or modification based on source audio context.

**Repaint Principle**

Repaint is based on **context completion** principle:
- Can complete **beginning**, **middle local**, **ending**, or **any region**
- Operation range: **3 seconds to 90 seconds**
- Model references source audio context information, generating within specified interval

**What Can You Do With It?**

1. **Local modification**: Modify lyrics, structure, or content in specified interval
2. **Change lyrics**: Maintain melody and orchestration, only change lyric content
3. **Change structure**: Change music structure in specified interval (e.g., change Verse to Chorus)
4. **Continue writing**: Continue writing beginning or ending based on context
5. **Clone timbre**: Clone source audio timbre characteristics based on context

**Advanced Repaint Usage**

You can use Repaint for more complex creative needs:

- **Infinite duration generation**:
  - Through multiple Repaint operations, can continuously extend audio, achieving infinite duration generation
  - Each continuation is based on previous segment's context, maintaining natural transitions and coherence
  - Can generate in segments, each 3–90 seconds, finally concatenate into complete work

- **Intelligent audio stitching**:
  - Intelligently organize and stitch two audios together
  - Use Repaint at first audio's end to continue, making transitions naturally connect
  - Or use Repaint to modify connection part between two audios for smooth transitions
  - Model automatically handles rhythm, harmony, timbre connections based on context, making stitched audio sound like a complete work

---

##### 4. Base Model Advanced Audio Control Tasks

In the **Base model**, we also support more advanced audio control tasks:

**Lego Task**: Intelligently add new tracks based on existing tracks
- Input an existing audio track (e.g., vocals)
- Model intelligently adds new tracks (e.g., drums, guitar, bass, etc.)
- New tracks coordinate with original tracks in rhythm and harmony

**Complete Task**: Add mixed tracks to single track
- Input a single-track audio (e.g., a cappella vocals)
- Model generates complete mixed accompaniment tracks
- Generated accompaniment matches vocals in style, rhythm, and harmony

**These advanced context completion tasks** greatly expand control methods, more intelligently providing inspiration and creativity.

---

The combination of these parameters determines what you "want." We'll explain input control **principles** and **techniques** in detail later.

### II. Inference Hyperparameters: How Does the Model Generate?

This is the part that affects "generation process behavior"—doesn't change what you want, but changes how the model does it.

**DiT (Diffusion Model) Hyperparameters:**

| Parameter | Function | Default | Tuning Advice |
|-----------|----------|---------|---------------|
| `inference_steps` | Diffusion steps | 8 (turbo) | More steps = finer but slower. Turbo uses 8, Base uses 32–100 |
| `guidance_scale` | CFG strength | 7.0 | Higher = more prompt adherence, but may overfit. Only Base model effective |
| `use_adg` | Adaptive Dual Guidance | False | After enabling, dynamically adjusts CFG, Base model only |
| `cfg_interval_start/end` | CFG effective interval | 0.0–1.0 | Controls which stage to apply CFG |
| `shift` | Timestep offset | 1.0 | Adjusts denoising trajectory, affects generation style |
| `infer_method` | Inference method | "ode" | `ode` deterministic, `sde` introduces randomness |
| `timesteps` | Custom timesteps | None | Advanced usage, overrides steps and shift |
| `audio_cover_strength` | Reference audio/codes influence strength | 1.0 | 0.0–1.0, higher = closer to reference, lower = more freedom |

**5Hz LM (Language Model) Hyperparameters:**

| Parameter | Function | Default | Tuning Advice |
|-----------|----------|---------|---------------|
| `thinking` | Enable CoT reasoning | True | Enable to let LM reason metadata and codes |
| `lm_temperature` | Sampling temperature | 0.85 | Higher = more random/creative, lower = more conservative/deterministic |
| `lm_cfg_scale` | LM CFG strength | 2.0 | Higher = more positive prompt adherence |
| `lm_top_k` | Top-K sampling | 0 | 0 means disabled, limits candidate word count |
| `lm_top_p` | Top-P sampling | 0.9 | Nucleus sampling, limits cumulative probability |
| `lm_negative_prompt` | Negative prompt | "NO USER INPUT" | Tells LM what not to generate |
| `use_cot_metas` | CoT reason metadata | True | Let LM auto-infer BPM, key, etc. |
| `use_cot_caption` | CoT rewrite caption | True | Let LM optimize your description |
| `use_cot_language` | CoT detect language | True | Let LM auto-detect vocal language |
| `use_constrained_decoding` | Constrained decoding | True | Ensures correct output format |

The combination of these parameters determines how the model "does it."

**About Parameter Tuning**

It's important to emphasize that **tuning factors and random factors sometimes have comparable influence**. When you adjust a parameter, it may be hard to tell if it's the parameter's effect or randomness causing the change.

Therefore, **we recommend fixing random factors when tuning**—by setting a fixed `seed` value, ensuring each generation starts from the same initial noise, so you can accurately feel the parameter's real impact on generated audio. Otherwise, parameter change effects may be masked by randomness, causing you to misjudge the parameter's role.

### III. Random Factors: Sources of Uncertainty

Even with identical inputs and hyperparameters, two generations may produce different results. This is because:

**1. DiT's Initial Noise**
- Diffusion models start from random noise and gradually denoise
- `seed` parameter controls this initial noise
- Different seed → different starting point → different endpoint

**2. LM's Sampling Randomness**
- When `lm_temperature > 0`, the sampling process itself has randomness
- Same prompt, each sampling may choose different tokens

**3. Additional Noise When `infer_method = "sde"`**
- SDE method injects additional randomness during denoising

---

#### Pros and Cons of Random Factors

Randomness is a double-edged sword.

**Benefits of Randomness:**
- **Explore creative space**: Same input can produce different variants, giving you more choices
- **Discover unexpected surprises**: Sometimes randomness brings excellent results you didn't expect
- **Avoid repetition**: Each generation is different, won't fall into single-pattern loops

**Challenges of Randomness:**
- **Uncontrollable results**: You can't precisely predict generation results, may generate multiple times without satisfaction
- **Hard to reproduce**: Even with identical inputs, hard to reproduce a specific good result
- **Tuning difficulty**: When adjusting parameters, hard to tell if it's parameter effect or randomness change
- **Screening cost**: Need to generate multiple versions to find satisfactory ones, increasing time cost

#### What Mindset to Face Random Factors?

**1. Accept Uncertainty**
- Randomness is an essential characteristic of AI music generation, not a bug, but a feature
- Don't expect every generation to be perfect; treat randomness as an exploration tool

**2. Embrace the Exploration Process**
- Treat generation process as "gacha" or "treasure hunting"—try multiple times, always find surprises
- Enjoy discovering unexpectedly good results, rather than obsessing over one-time success

**3. Use Fixed Seed Wisely**
- When you want to **understand parameter effects**, fix `seed` to eliminate randomness interference
- When you want to **explore creative space**, let `seed` vary randomly

**4. Batch Generation + Intelligent Screening**
- Don't rely on single generation; batch generate multiple versions
- Use automatic scoring mechanisms for initial screening to improve efficiency

#### Our Solution: Large Batch + Automatic Scoring

Because our inference is extremely fast, if your GPU VRAM is sufficient, you can explore random space through **large batch**:

- **Batch generation**: Generate multiple versions at once (e.g., batch_size=2,4,8), quickly explore random space
- **Automatic scoring mechanism**: We provide automatic scoring mechanisms that can help you initially screen, doing **test time scaling**

**Automatic Scoring Mechanism**

We provide multiple scoring metrics, among which **my favorite is DiT Lyrics Alignment Score**:

- **DiT Lyrics Alignment Score**: This score implicitly affects lyric accuracy
  - It evaluates the alignment degree between lyrics and audio in generated audio
  - Higher score means lyrics are more accurately positioned in audio, better match between singing and lyrics
  - This is particularly important for music generation with lyrics, can help you screen versions with higher lyric accuracy

- **Other scoring metrics**: Also include other quality assessment metrics, can evaluate generation results from multiple dimensions

**Recommended Workflow:**

1. **Batch generation**: Set larger `batch_size` (e.g., 2, 4, 8), generate multiple versions at once
2. **Enable AutoGen**: Enable automatic generation, let system continuously generate new batches in background
   - **AutoGen mechanism**: AutoGen automatically uses same parameters (but random seed) to generate next batch in background while you're viewing current batch results
   - This lets you continuously explore random space without manually clicking generate button
   - Each new batch uses new random seed, ensuring result diversity
3. **Automatic scoring**: Enable automatic scoring, let system automatically score each version
4. **Initial screening**: Screen versions with higher scores based on DiT Lyrics Alignment Score and other metrics
5. **Manual selection**: Manually select the final version that best meets your needs from screened versions

This fully utilizes randomness to explore creative space while improving efficiency through automation tools, avoiding blind searching in large generation results. AutoGen lets you "generate while listening"—while browsing current results, the next batch is already prepared in the background.

---

## Conclusion

This tutorial currently covers ACE-Step 1.5's core concepts and usage methods:

- **Mental Models**: Understanding human-centered generation design philosophy
- **Model Architecture**: Understanding how LM and DiT work together
- **Input Control**: Mastering text (Caption, Lyrics, metadata) and audio (reference audio, source audio) control methods
- **Inference Hyperparameters**: Understanding parameters affecting generation process
- **Random Factors**: Learning to use randomness to explore creative space, improving efficiency through Large Batch + AutoGen + Automatic Scoring

This is just the beginning. There's much more content we want to share with you:

- More Prompting tips and practical cases
- Detailed usage guides for different task types
- Advanced techniques and creative workflows
- Common issues and solutions
- Performance optimization suggestions

**This tutorial will continue to be updated and improved.** If you have any questions or suggestions during use, feedback is welcome. Let's make ACE-Step your creative partner in your pocket together.

---

*To be continued...*
