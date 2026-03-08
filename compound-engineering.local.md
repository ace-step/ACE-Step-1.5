---
review_agents: [kieran-python-reviewer, code-simplicity-reviewer, security-sentinel, performance-oracle]
plan_review_agents: [kieran-python-reviewer, code-simplicity-reviewer]
---

# Review Context

This is ACE-Step, a music generation ML project using PyTorch and Gradio.

- This is a GPU-intensive inference project -- focus on GPU memory management and model inference performance
- The UI is built with Gradio -- check for proper component wiring and state management
- Audio processing is central -- watch for memory leaks in tensor operations and audio buffer handling
- Model loading/unloading patterns matter -- ensure proper CUDA memory cleanup
