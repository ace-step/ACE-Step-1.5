# ACE-Step Project Overview

> For installation instructions, see [README.md](README.md)

## Links

- [Project Page](https://ace-step.github.io/ace-step-v1.5.github.io/)
- [Hugging Face](https://huggingface.co/ACE-Step/Ace-Step1.5)
- [ModelScope](https://modelscope.cn/models/ACE-Step/Ace-Step1.5)
- [Space Demo](https://huggingface.co/spaces/ACE-Step/Ace-Step-v1.5)
- [Discord](https://discord.gg/PeWDxrkdj7)
- [Technical Report](https://arxiv.org/abs/2602.00744)

## Abstract

ACE-Step v1.5 is a highly efficient open-source music foundation model that brings commercial-grade generation to consumer hardware. Key highlights:

- Quality beyond most commercial music models
- Under 2 seconds per full song on A100, under 10 seconds on RTX 3090
- Runs locally with less than 4GB of VRAM
- Supports lightweight LoRA personalization from just a few songs

The architecture combines a Language Model (LM) as an omni-capable planner with a Diffusion Transformer (DiT). The LM transforms simple user queries into comprehensive song blueprints—scaling from short loops to 10-minute compositions.

## Features

### Performance
- **Ultra-Fast Generation** — Under 2s per full song on A100
- **Flexible Duration** — 10 seconds to 10 minutes (600s)
- **Batch Generation** — Up to 8 songs simultaneously

### Generation Quality
- **Commercial-Grade Output** — Between Suno v4.5 and Suno v5
- **Rich Style Support** — 1000+ instruments and styles
- **Multi-Language Lyrics** — 50+ languages

### Capabilities

| Feature | Description |
|---------|-------------|
| Reference Audio Input | Use reference audio to guide style |
| Cover Generation | Create covers from existing audio |
| Repaint & Edit | Selective local audio editing |
| Track Separation | Separate into individual stems |
| Vocal2BGM | Auto-generate accompaniment |
| Metadata Control | Duration, BPM, key/scale, time signature |
| Simple Mode | Full songs from simple descriptions |
| LoRA Training | 8 songs, 1 hour on 3090 (12GB VRAM) |

## Architecture

The system uses a hybrid LM + DiT architecture:
- **LM (Language Model)**: Plans metadata, lyrics, captions via Chain-of-Thought
- **DiT (Diffusion Transformer)**: Generates audio from the LM's blueprint

## Model Zoo

### DiT Models

| Model | Steps | Quality | Diversity | HuggingFace |
|-------|:-----:|:-------:|:---------:|-------------|
| `acestep-v15-base` | 50 | Medium | High | [Link](https://huggingface.co/ACE-Step/acestep-v15-base) |
| `acestep-v15-sft` | 50 | High | Medium | [Link](https://huggingface.co/ACE-Step/acestep-v15-sft) |
| `acestep-v15-turbo` | 8 | Very High | Medium | [Link](https://huggingface.co/ACE-Step/Ace-Step1.5) |

### LM Models

| Model | Audio Understanding | Composition | HuggingFace |
|-------|:------------------:|:-----------:|-------------|
| `acestep-5Hz-lm-0.6B` | Medium | Medium | [Link](https://huggingface.co/ACE-Step/acestep-5Hz-lm-0.6B) |
| `acestep-5Hz-lm-1.7B` | Medium | Medium | [Link](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| `acestep-5Hz-lm-4B` | Strong | Strong | [Link](https://huggingface.co/ACE-Step/acestep-5Hz-lm-4B) |

## License

This project is licensed under [MIT](https://github.com/ACE-Step/ACE-Step-1.5/blob/main/LICENSE).

## Citation

```BibTeX
@misc{gong2026acestep,
    title={ACE-Step 1.5: Pushing the Boundaries of Open-Source Music Generation},
    author={Junmin Gong, Yulin Song, Wenxiao Zhao, Sen Wang, Shengyuan Xu, Jing Guo},
    howpublished={\url{https://github.com/ace-step/ACE-Step-1.5}},
    year={2026}
}
```
