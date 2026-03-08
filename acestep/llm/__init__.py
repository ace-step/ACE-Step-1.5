"""``acestep.llm`` – LLM inference subpackage.

The primary public API is :class:`LLMHandler`, which lives in
``acestep.llm_inference`` and combines the backend mixins defined
in this package.  Import it from either location::

    from acestep.llm_inference import LLMHandler   # canonical
    from acestep.llm import LLMHandler              # convenience alias
"""

from acestep.llm.constants import (  # noqa: F401
    BYTES_PER_GB,
    CODES_PER_SECOND,
    CODES_PHASE_TOKEN_BUFFER,
    COT_PHASE_TOKEN_BUFFER,
    DEFAULT_MAX_MODEL_LEN,
    LOW_GPU_MAX_MODEL_LEN,
    MODEL_LEN_HEADROOM,
    VRAM_SAFE_FREE_GB,
)
from acestep.llm.mlx_backend import MlxBackendMixin  # noqa: F401
from acestep.llm.memory import MemoryMixin  # noqa: F401
from acestep.llm.pt_backend import PytorchBackendMixin  # noqa: F401
from acestep.llm.vllm_backend import VllmBackendMixin  # noqa: F401


def __getattr__(name: str):
    """Lazily import ``LLMHandler`` to avoid circular imports."""
    if name == "LLMHandler":
        from acestep.llm_inference import LLMHandler

        return LLMHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
