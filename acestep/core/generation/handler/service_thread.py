"""Long-lived daemon threads that run ``service_generate`` calls.

``generate_music`` used to start a fresh thread for every generation. On Windows that leaks
host RAM when the DiT is offloaded to the CPU between generations: PyTorch's Windows builds
allocate CPU tensors with mimalloc, which abandons a thread's heap when the thread exits. Each
generation's thread re-allocated the DiT's CPU copy, and once that thread had exited, the memory
was not reused after a later thread freed it (+4-12 GB of private memory per generation with
the XL DiT, until the process crashed).

Here every call runs on an idle long-lived thread, so sequential generations reuse the same
one. A new thread starts only when every existing one is busy (concurrent requests, or a call
still running past its timeout), so concurrency and timeouts behave as before. The threads are
daemons, unlike ``ThreadPoolExecutor`` workers, so a hung CUDA call can't block interpreter exit.
"""

import queue
import threading
from typing import Callable, List, Optional, Tuple

from loguru import logger

_Job = Tuple[Callable[[], None], threading.Event]

_idle_workers: List["queue.SimpleQueue[_Job]"] = []
_idle_lock = threading.Lock()


def _run_logged(fn: Callable[[], None]) -> None:
    """Run ``fn``, logging an escaping exception instead of ending the worker thread."""
    try:
        fn()
    except Exception:  # callers capture their own errors; this only keeps the worker alive
        logger.exception("[service_thread] Unhandled error in service call")


def _serve(jobs: "queue.SimpleQueue[_Job]") -> None:
    """Run this worker's jobs forever, signalling each job's event when it ends."""
    while True:
        fn, done = jobs.get()
        try:
            _run_logged(fn)
            # Don't keep the call's closure (inputs, outputs, exception frames) alive while idle.
            fn = None
            # Rejoin the idle pool before signalling, so the caller's next call reuses this thread.
            with _idle_lock:
                _idle_workers.append(jobs)
        finally:
            done.set()


def _acquire_worker() -> "queue.SimpleQueue[_Job]":
    """Return an idle worker's job queue, starting a new worker thread if none is idle."""
    with _idle_lock:
        if _idle_workers:
            return _idle_workers.pop()
    jobs: "queue.SimpleQueue[_Job]" = queue.SimpleQueue()
    threading.Thread(target=_serve, args=(jobs,), name="service-generate", daemon=True).start()
    return jobs


def run_on_service_thread(fn: Callable[[], None], timeout: Optional[float]) -> bool:
    """Run ``fn`` on a long-lived service thread and wait for it.

    Args:
        fn: Zero-argument callable; it should store its own result or exception.
        timeout: Seconds to wait, or None to wait forever.

    Returns:
        True if ``fn`` finished within ``timeout``, False if it is still running.
    """
    done = threading.Event()
    _acquire_worker().put((fn, done))
    return done.wait(timeout)
