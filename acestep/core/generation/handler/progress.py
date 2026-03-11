"""Progress estimation mixin for AceStepHandler."""

import json
import os
import threading
import time
from typing import Optional

from loguru import logger

# Conservative per-step estimate used when no historical timing data exists
# (i.e., first-ever generation on this machine).  2.5s/step is deliberately
# slow so the progress bar undershoots rather than overshoots — reaching 79%
# early and pausing is far less alarming than freezing at 52% with zero
# movement.  The estimate self-corrects after the first successful generation.
_FALLBACK_PER_STEP_SEC = 2.5


class ProgressMixin:
    def _get_project_root(self) -> str:
        """Get project root directory path.

        Returns the directory set by the ``ACESTEP_PROJECT_ROOT`` environment
        variable when present, otherwise the current working directory.  Using
        the working directory (rather than ``__file__``) keeps generated cache
        files and the checkpoints folder next to where the user launched the
        process, regardless of whether the package was installed via
        ``pip install .`` or run from source.
        """
        env_root = os.environ.get("ACESTEP_PROJECT_ROOT")
        if env_root:
            return os.path.abspath(env_root)
        return os.getcwd()

    def _load_progress_estimates(self) -> None:
        """Load persisted diffusion progress estimates if available."""
        try:
            if os.path.exists(self._progress_estimates_path):
                with open(self._progress_estimates_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and isinstance(data.get("records"), list):
                        self._progress_estimates = data
        except Exception:
            # Ignore corrupted cache; it will be overwritten on next save.
            self._progress_estimates = {"records": []}

    def _save_progress_estimates(self) -> None:
        """Persist diffusion progress estimates."""
        try:
            os.makedirs(os.path.dirname(self._progress_estimates_path), exist_ok=True)
            with open(self._progress_estimates_path, "w", encoding="utf-8") as f:
                json.dump(self._progress_estimates, f)
        except Exception:
            pass

    def _duration_bucket(self, duration_sec: Optional[float]) -> str:
        if duration_sec is None or duration_sec <= 0:
            return "unknown"
        if duration_sec <= 60:
            return "short"
        if duration_sec <= 180:
            return "medium"
        if duration_sec <= 360:
            return "long"
        return "xlong"

    def _update_progress_estimate(
        self,
        per_step_sec: float,
        infer_steps: int,
        batch_size: int,
        duration_sec: Optional[float],
    ) -> None:
        if per_step_sec <= 0 or infer_steps <= 0:
            return
        record = {
            "device": self.device,
            "infer_steps": int(infer_steps),
            "batch_size": int(batch_size),
            "duration_sec": float(duration_sec) if duration_sec and duration_sec > 0 else None,
            "duration_bucket": self._duration_bucket(duration_sec),
            "per_step_sec": float(per_step_sec),
            "updated_at": time.time(),
        }
        with self._progress_estimates_lock:
            records = self._progress_estimates.get("records", [])
            records.append(record)
            # Keep recent 100 records
            records = records[-100:]
            self._progress_estimates["records"] = records
            self._progress_estimates["updated_at"] = time.time()
            self._save_progress_estimates()

    def _estimate_diffusion_per_step(
        self,
        infer_steps: int,
        batch_size: int,
        duration_sec: Optional[float],
    ) -> Optional[float]:
        # Prefer most recent exact-ish record
        target_bucket = self._duration_bucket(duration_sec)
        with self._progress_estimates_lock:
            records = list(self._progress_estimates.get("records", []))
        if not records:
            return None

        # Filter by device first
        device_records = [r for r in records if r.get("device") == self.device] or records

        # Exact match by steps/batch/bucket
        for r in reversed(device_records):
            if (
                r.get("infer_steps") == infer_steps
                and r.get("batch_size") == batch_size
                and r.get("duration_bucket") == target_bucket
            ):
                return r.get("per_step_sec")

        # Same steps + bucket, scale by batch and duration when possible
        for r in reversed(device_records):
            if r.get("infer_steps") == infer_steps and r.get("duration_bucket") == target_bucket:
                base = r.get("per_step_sec")
                base_batch = r.get("batch_size", batch_size)
                base_dur = r.get("duration_sec")
                if base and base_batch:
                    est = base * (batch_size / base_batch)
                    if duration_sec and base_dur:
                        est *= (duration_sec / base_dur)
                    return est

        # Same steps, scale by batch and duration ratio if available
        for r in reversed(device_records):
            if r.get("infer_steps") == infer_steps:
                base = r.get("per_step_sec")
                base_batch = r.get("batch_size", batch_size)
                base_dur = r.get("duration_sec")
                if base and base_batch:
                    est = base * (batch_size / base_batch)
                    if duration_sec and base_dur:
                        est *= (duration_sec / base_dur)
                    return est

        # Fallback to global median
        per_steps = [r.get("per_step_sec") for r in device_records if r.get("per_step_sec")]
        if per_steps:
            per_steps.sort()
            return per_steps[len(per_steps) // 2]
        return None

    def _start_diffusion_progress_estimator(
        self,
        progress,
        start: float,
        end: float,
        infer_steps: int,
        batch_size: int,
        duration_sec: Optional[float],
        desc: str,
    ):
        """Best-effort progress updates during diffusion using previous step timing.

        Falls back to a conservative default estimate when no historical data
        exists (first-ever generation).  This ensures the progress bar always
        moves during Phase 2 instead of freezing at 52%.
        """
        if progress is None or infer_steps <= 0:
            return None, None
        per_step = self._estimate_diffusion_per_step(
            infer_steps=infer_steps,
            batch_size=batch_size,
            duration_sec=duration_sec,
        ) or self._last_diffusion_per_step_sec

        if not per_step or per_step <= 0:
            # No history at all — use conservative fallback so progress bar
            # still moves on first run.  Scale by batch size for a rough
            # approximation.
            per_step = _FALLBACK_PER_STEP_SEC * max(1, batch_size)
            logger.info(
                f"[progress] No timing history — using fallback estimate "
                f"({per_step:.1f}s/step for batch_size={batch_size}).  "
                f"This will self-calibrate after the first generation."
            )

        expected = per_step * infer_steps
        if expected <= 0:
            return None, None
        stop_event = threading.Event()

        def _runner():
            start_time = time.time()
            while not stop_event.is_set():
                elapsed = time.time() - start_time
                frac = min(0.999, elapsed / expected)
                value = start + (end - start) * frac
                try:
                    progress(value, desc=desc)
                except Exception:
                    pass
                stop_event.wait(0.5)

        thread = threading.Thread(target=_runner, name="diffusion-progress", daemon=True)
        thread.start()
        return stop_event, thread