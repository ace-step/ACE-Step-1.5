"""Shared constants for the ``acestep.llm`` subpackage."""

# Minimum free VRAM (GB) required to attempt vLLM initialization.
# vLLM's KV cache allocator adapts to available memory, so we only need a
# basic sanity check -- not a hard total-VRAM gate.
VRAM_SAFE_FREE_GB = 2.0

# Audio codes are generated at 5 codes per second of audio
CODES_PER_SECOND = 5

# Token buffers for each generation phase
CODES_PHASE_TOKEN_BUFFER = 10    # small buffer since constrained decoder forces EOS
COT_PHASE_TOKEN_BUFFER = 500     # larger buffer for metadata overhead

# Tokens reserved from max_model_len to avoid overflow
MODEL_LEN_HEADROOM = 64

# Byte-to-GB conversion factor
BYTES_PER_GB = 1024 ** 3

# Max model context length by GPU tier
LOW_GPU_MAX_MODEL_LEN = 2048
DEFAULT_MAX_MODEL_LEN = 4096
