"""Execution helper for ``generate_music`` service invocation with progress tracking."""

import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

import threading
from loguru import logger

from .runtime_progress_relay import RuntimeProgressRelay

# Maximum wall-clock seconds to wait for service_generate before declaring a hang.
# Generous default: most generations finish in 30-120s, but large batches on slow
# GPUs can take several minutes.  Override via ACESTEP_GENERATION_TIMEOUT env var.
_DEFAULT_GENERATION_TIMEOUT = int(os.environ.get("ACESTEP_GENERATION_TIMEOUT", "600"))


class GenerateMusicExecuteMixin:
    """Run service generation under diffusion progress estimation lifecycle."""

    def _run_generate_music_service_with_progress(
        self,
        progress: Any,
        actual_batch_size: int,
        audio_duration: Optional[float],
        inference_steps: int,
        timesteps: Optional[Sequence[float]],
        service_inputs: Dict[str, Any],
        refer_audios: Optional[List[Any]],
        guidance_scale: float,
        actual_seed_list: Optional[List[int]],
        audio_cover_strength: float,
        cover_noise_strength: float,
        use_adg: bool,
        cfg_interval_start: float,
        cfg_interval_end: float,
        shift: float,
        infer_method: str,
        sampler_mode: str = "euler",
        velocity_norm_threshold: float = 0.0,
        velocity_ema_factor: float = 0.0,
        repaint_crossfade_frames: int = 10,
        repaint_injection_ratio: float = 0.5,
    ) -> Dict[str, Any]:
        """Invoke ``service_generate`` while maintaining background progress estimation.

        Wraps the synchronous CUDA call in a monitored thread so that a hung
        diffusion loop becomes a recoverable ``TimeoutError`` instead of a
        permanent UI freeze.
        """
        infer_steps_for_progress = len(timesteps) if timesteps else inference_steps
        progress_desc = f"Generating music (batch size: {actual_batch_size})..."
        stop_event = None
        progress_thread = None
        relay = RuntimeProgressRelay(progress=progress, start=0.52, end=0.79)
        relay.emit_progress(0.52, progress_desc)

        # --- Timeout-wrapped service_generate ---
        # Run the actual CUDA work in a child thread so we can join() with a
        # deadline.  If it exceeds the timeout the calling thread unblocks and
        # raises TimeoutError, which propagates to generate_music()'s
        # try/except and becomes a clean error payload for the UI.
        _result: Dict[str, Any] = {}
        _error: Dict[str, BaseException] = {}

        def _service_target():
            try:
                _result["outputs"] = self.service_generate(
                    captions=service_inputs["captions_batch"],
                    global_captions=service_inputs.get("global_captions_batch"),
                    lyrics=service_inputs["lyrics_batch"],
                    metas=service_inputs["metas_batch"],
                    vocal_languages=service_inputs["vocal_languages_batch"],
                    refer_audios=refer_audios,
                    target_wavs=service_inputs["target_wavs_tensor"],
                    infer_steps=inference_steps,
                    guidance_scale=guidance_scale,
                    seed=actual_seed_list,
                    repainting_start=service_inputs["repainting_start_batch"],
                    repainting_end=service_inputs["repainting_end_batch"],
                    instructions=service_inputs["instructions_batch"],
                    audio_cover_strength=audio_cover_strength,
                    cover_noise_strength=cover_noise_strength,
                    use_adg=use_adg,
                    cfg_interval_start=cfg_interval_start,
                    cfg_interval_end=cfg_interval_end,
                    shift=shift,
                    infer_method=infer_method,
                    sampler_mode=sampler_mode,
                    velocity_norm_threshold=velocity_norm_threshold,
                    velocity_ema_factor=velocity_ema_factor,
                    audio_code_hints=service_inputs["audio_code_hints_batch"],
                    return_intermediate=service_inputs["should_return_intermediate"],
                    timesteps=timesteps,
                    chunk_mask_modes=service_inputs.get("chunk_mask_modes_batch"),
                    repaint_crossfade_frames=repaint_crossfade_frames,
                    repaint_injection_ratio=repaint_injection_ratio,
                    progress_callback=relay.enqueue,
                )
            except Exception as exc:
                _error["exc"] = exc

        def _stop_progress_estimator_if_finished() -> None:
            """Stop the estimator thread but keep its handle until it actually exits."""
            nonlocal progress_thread
            progress_thread = RuntimeProgressRelay.stop_estimator_if_finished(progress_thread)

        try:
            stop_event, progress_thread = self._start_diffusion_progress_estimator(
                progress=relay.emit_progress,
                start=0.52,
                end=0.79,
                infer_steps=infer_steps_for_progress,
                batch_size=actual_batch_size,
                duration_sec=audio_duration if audio_duration and audio_duration > 0 else None,
                desc=progress_desc,
            )

            gen_thread = threading.Thread(
                target=_service_target,
                name="service-generate",
                daemon=True,
            )
            gen_thread.start()
            deadline = time.monotonic() + _DEFAULT_GENERATION_TIMEOUT
            poll_interval = 0.1
            saw_runtime_progress = False
            while gen_thread.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                gen_thread.join(timeout=min(poll_interval, remaining))
                drained_runtime_progress = relay.drain()
                if drained_runtime_progress and not saw_runtime_progress:
                    saw_runtime_progress = True
                    if stop_event is not None:
                        stop_event.set()
                    _stop_progress_estimator_if_finished()
                if not gen_thread.is_alive():
                    break

            drained_runtime_progress = relay.drain()
            if drained_runtime_progress and not saw_runtime_progress:
                saw_runtime_progress = True
                if stop_event is not None:
                    stop_event.set()
                _stop_progress_estimator_if_finished()

            if gen_thread.is_alive():
                logger.error(
                    f"[generate_music] service_generate exceeded {_DEFAULT_GENERATION_TIMEOUT}s "
                    f"timeout (batch={actual_batch_size}, steps={inference_steps}, "
                    f"duration={audio_duration}s).  The CUDA operation may still be "
                    f"running in the background."
                )
                raise TimeoutError(
                    f"Music generation timed out after {_DEFAULT_GENERATION_TIMEOUT} seconds.  "
                    f"This usually means the GPU ran out of VRAM or the diffusion loop "
                    f"stalled.  Try reducing batch size, duration, or inference steps."
                )
            if "exc" in _error:
                raise _error["exc"]
            relay.emit_progress(0.79, progress_desc)

        finally:
            relay.shutdown()
            if stop_event is not None:
                stop_event.set()
            if progress_thread is not None:
                progress_thread.join(timeout=1.0)

        return {"outputs": _result["outputs"], "infer_steps_for_progress": infer_steps_for_progress}
