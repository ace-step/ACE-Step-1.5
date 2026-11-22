"""Serialize 5Hz LM generation calls on a shared ``LLMHandler``.

``LLMHandler`` keeps one ``MetadataConstrainedLogitsProcessor`` and resets it
at the start of every LM call. With concurrent API workers, a second job's
reset could land while the first job was still decoding audio codes. That
cleared the first job's code counter and EOS block and cut its audio short.
The engine lock in nano-vllm does not help, because setup runs before it.
"""

import functools
import threading
from typing import Any, Callable, TypeVar

_Method = TypeVar("_Method", bound=Callable[..., Any])


def create_lm_generation_lock() -> threading.RLock:
    """Create the per-handler lock used by :func:`serialize_lm_generation`.

    Returns:
        A re-entrant lock, so a backend may fall back to another backend
        on the same thread without deadlocking.
    """

    return threading.RLock()


def serialize_lm_generation(method: _Method) -> _Method:
    """Run a handler method while holding ``self._lm_generation_lock``.

    The lock covers processor setup, decoding and output parsing, so each
    call owns the shared constrained processor from reset to finish.

    Args:
        method: An ``LLMHandler`` method that sets up and uses the shared
            constrained processor.

    Returns:
        The wrapped method.
    """

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._lm_generation_lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
