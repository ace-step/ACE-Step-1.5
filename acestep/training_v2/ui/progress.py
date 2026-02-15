"""
Live training progress display using Rich.

Renders a live-updating dashboard that shows:
    - Epoch progress bar with ETA
    - Step-level progress bar within the current epoch
    - Current metrics (loss, learning rate, speed)
    - GPU VRAM usage bar
    - Scrolling log of recent messages

Falls back to plain ``print(msg)`` when Rich is unavailable or stdout
is not a TTY.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from acestep.training_v2.ui import TrainingUpdate, console, is_rich_active
from acestep.training_v2.ui.gpu_monitor import GPUMonitor


# ---- Logging capture (prevents ghost panels in tmux / web terminals) --------

class _LiveLogCapture(logging.Handler):
    """Redirects log messages into the panel's scrolling log area.

    During a Rich Live session, any direct writes to stderr (including
    from Python's ``logging.StreamHandler``) break the ANSI cursor
    positioning that Live uses to overwrite the panel in-place.  This
    causes "ghost panels" — stale copies of the display that get pushed
    up.  The problem is especially visible in tmux and web terminals.

    This handler captures log messages into the ``recent_msgs`` list
    that the panel display reads from, and a ``live`` reference so the
    display refreshes immediately after the log message is captured.
    The file handler (``sidestep.log``) is unaffected and keeps logging
    normally.
    """

    def __init__(self, messages: list, live: object = None) -> None:
        super().__init__(level=logging.INFO)
        self._messages = messages
        self._live = live

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            self._messages.append(msg)
            if len(self._messages) > 20:
                self._messages.pop(0)
        except Exception:
            pass


# ---- Training statistics tracker --------------------------------------------

@dataclass
class TrainingStats:
    """Accumulates statistics during training for the live display and
    the post-training summary.
    """

    start_time: float = 0.0
    first_loss: float = 0.0
    best_loss: float = float("inf")
    last_loss: float = 0.0
    last_lr: float = 0.0
    _lr_seen: bool = False
    current_epoch: int = 0
    max_epochs: int = 0
    current_step: int = 0
    total_steps_estimate: int = 0
    steps_this_session: int = 0
    peak_vram_mb: float = 0.0
    last_epoch_time: float = 0.0
    steps_per_epoch: int = 0
    """Total optimizer steps per epoch (for step-level progress bar)."""
    step_in_epoch: int = 0
    """Current step index within the epoch (resets each epoch)."""
    _step_times: list = field(default_factory=list)
    checkpoints: List[Dict[str, object]] = field(default_factory=list)
    """Saved checkpoints: ``[{"epoch": int, "loss": float, "path": str}, ...]``."""

    @property
    def elapsed(self) -> float:
        if self.start_time <= 0:
            return 0.0
        return time.time() - self.start_time

    @property
    def elapsed_str(self) -> str:
        return _fmt_duration(self.elapsed)

    @property
    def samples_per_sec(self) -> float:
        if not self._step_times or len(self._step_times) < 2:
            return 0.0
        dt = self._step_times[-1] - self._step_times[0]
        if dt <= 0:
            return 0.0
        return (len(self._step_times) - 1) / dt

    @property
    def eta_seconds(self) -> float:
        if self.max_epochs <= 0 or self.current_epoch <= 0:
            return 0.0
        elapsed = self.elapsed
        if elapsed <= 0:
            return 0.0
        progress = self.current_epoch / self.max_epochs
        if progress <= 0:
            return 0.0
        return elapsed * (1.0 / progress - 1.0)

    @property
    def eta_str(self) -> str:
        eta = self.eta_seconds
        if eta <= 0:
            return "--"
        return _fmt_duration(eta)

    def record_step(self) -> None:
        now = time.time()
        self._step_times.append(now)
        if len(self._step_times) > 50:
            self._step_times = self._step_times[-50:]


def _fmt_duration(seconds: float) -> str:
    """Format seconds to ``1h 23m 45s`` or ``12m 34s`` or ``45s``."""
    if seconds < 0:
        return "--"
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ---- Rich live display builder ----------------------------------------------

_LOG_LINES = 5  # Fixed number of log lines for stable panel height


def _build_display(
    stats: TrainingStats,
    gpu: GPUMonitor,
    recent_msgs: list,
) -> Any:
    """Build the composite Rich renderable for one Live refresh."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.progress_bar import ProgressBar
    from rich.table import Table
    from rich.text import Text

    # -- Epoch progress -------------------------------------------------------
    epoch_pct = 0.0
    if stats.max_epochs > 0:
        epoch_pct = stats.current_epoch / stats.max_epochs
    epoch_bar = ProgressBar(total=100, completed=int(epoch_pct * 100), width=40)

    epoch_line = Text()
    epoch_line.append("  Epoch ", style="dim")
    epoch_line.append(f"{stats.current_epoch}", style="bold")
    epoch_line.append(f" / {stats.max_epochs}  ", style="dim")
    epoch_line.append_text(Text.from_markup(f"  Step {stats.current_step}"))
    epoch_line.append(f"  |  ETA {stats.eta_str}", style="dim")

    # -- Step-level progress (within epoch) -----------------------------------
    # Only show the inner step bar when there are enough steps per epoch
    # to make it meaningful.  For small datasets (e.g. 3 steps/epoch) the
    # bar just flickers up/down and is more confusing than helpful.
    _MIN_STEPS_FOR_BAR = 10
    step_parts: list = []
    if stats.steps_per_epoch >= _MIN_STEPS_FOR_BAR:
        shown_step = max(stats.step_in_epoch, 0)
        step_pct = min(shown_step / stats.steps_per_epoch, 1.0)
        step_bar = ProgressBar(
            total=100, completed=int(step_pct * 100), width=30,
        )
        step_line = Text()
        step_line.append(f"  Step {shown_step}", style="dim")
        step_line.append(f" / {stats.steps_per_epoch}  ", style="dim")
        step_line.append_text(
            Text.from_markup(f"  {step_bar}  [dim]{step_pct * 100:.0f}%[/]"),
        )
        step_parts = [step_line]

    # -- Metrics table --------------------------------------------------------
    metrics = Table(
        show_header=False, show_edge=False, pad_edge=False,
        box=None, expand=True,
    )
    metrics.add_column("key", style="dim", ratio=1)
    metrics.add_column("val", ratio=1)
    metrics.add_column("key2", style="dim", ratio=1)
    metrics.add_column("val2", ratio=1)

    loss_str = f"{stats.last_loss:.4f}" if stats.last_loss > 0 else "--"
    best_str = f"{stats.best_loss:.4f}" if stats.best_loss < float("inf") else "--"
    lr_str = f"{stats.last_lr:.2e}" if stats._lr_seen else "--"
    speed_str = (
        f"{stats.samples_per_sec:.1f} steps/s"
        if stats.samples_per_sec > 0 else "--"
    )

    metrics.add_row("Loss", f"[bold]{loss_str}[/]", "Best", f"[green]{best_str}[/]")
    metrics.add_row("LR", lr_str, "Speed", speed_str)
    metrics.add_row(
        "Elapsed", stats.elapsed_str,
        "Epoch time",
        f"{stats.last_epoch_time:.1f}s" if stats.last_epoch_time > 0 else "--",
    )

    # -- VRAM bar -------------------------------------------------------------
    if gpu.available:
        snap = gpu.snapshot()
        pct = snap.percent
        bar_width = 30
        filled = int(bar_width * pct / 100)
        bar_color = "green" if pct < 70 else ("yellow" if pct < 90 else "red")
        bar = f"[{bar_color}]{'#' * filled}[/][dim]{'-' * (bar_width - filled)}[/]"
        vram_line = (
            f"  VRAM {bar}  "
            f"{snap.used_gb:.1f} / {snap.total_gb:.1f} GiB  "
            f"[dim]({pct:.0f}%)[/]"
        )
    else:
        vram_line = "  [dim]VRAM monitoring not available[/]"

    # -- Recent log (fixed height for stable panel) ---------------------------
    log_text = Text()
    padded = recent_msgs[-_LOG_LINES:]
    while len(padded) < _LOG_LINES:
        padded.insert(0, "")
    for msg in padded:
        if not msg:
            log_text.append("  \n")
        elif msg.startswith("[OK]"):
            log_text.append(f"  {msg}\n", style="green")
        elif msg.startswith("[WARN]"):
            log_text.append(f"  {msg}\n", style="yellow")
        elif msg.startswith("[FAIL]"):
            log_text.append(f"  {msg}\n", style="red")
        elif msg.startswith("[INFO]"):
            log_text.append(f"  {msg}\n", style="blue")
        else:
            log_text.append(f"  {msg}\n", style="dim")

    # -- Assemble panel -------------------------------------------------------
    parts: list = [
        epoch_line,
        Text(""),
        Text.from_markup(f"  {epoch_bar}  [dim]{epoch_pct * 100:.0f}%[/]"),
    ]
    parts.extend(step_parts)
    parts.extend([
        Text(""),
        metrics,
        Text(""),
        Text.from_markup(vram_line),
        Text(""),
        log_text,
    ])

    return Panel(
        Group(*parts),
        title="[bold]Side-Step Training Progress[/]",
        border_style="green",
        padding=(0, 1),
    )


# ---- Main entry point -------------------------------------------------------

def track_training(
    training_iter: Iterator[Union[Tuple[int, float, str], TrainingUpdate]],
    max_epochs: int,
    device: str = "cuda:0",
    refresh_per_second: int = 2,
) -> TrainingStats:
    """Consume training yields and display live progress.

    Args:
        training_iter: Generator yielding ``(step, loss, msg)`` or
            ``TrainingUpdate`` objects.
        max_epochs: Total number of epochs (for progress bar).
        device: Device string for GPU monitoring.
        refresh_per_second: Rich Live refresh rate.

    Returns:
        Final ``TrainingStats`` for the summary display.
    """
    stats = TrainingStats(start_time=time.time(), max_epochs=max_epochs)
    gpu = GPUMonitor(device=device, interval=3.0)
    recent_msgs: list[str] = []

    if is_rich_active() and console is not None:
        return _track_rich(training_iter, stats, gpu, recent_msgs, refresh_per_second)
    return _track_plain(training_iter, stats, gpu, recent_msgs)


def _track_rich(
    training_iter: Iterator,
    stats: TrainingStats,
    gpu: GPUMonitor,
    recent_msgs: list,
    refresh_per_second: int,
) -> TrainingStats:
    """Rich Live display loop.

    Uses ``transient=True`` so each frame cleanly erases the previous one,
    preventing ghost-panel stacking when external code (e.g. Lightning's
    SLURM warning) writes to stdout/stderr during the live display.

    During the Live session, Python logging is redirected from stderr into
    the panel's scrolling log area.  This prevents log output (e.g. from
    checkpoint saves) from breaking Rich's ANSI cursor positioning, which
    caused "ghost panels" — especially in tmux and web terminals.  The file
    handler (sidestep.log) is unaffected.

    After the Live context exits, the final dashboard is re-printed as a
    static renderable so it remains visible in the terminal.
    """
    import warnings
    from rich.live import Live

    assert console is not None

    error_msgs: list[str] = []

    # Suppress warnings that print to stderr during Live and disrupt
    # Rich's cursor positioning (e.g. Lightning SLURM, fork safety).
    warnings.filterwarnings(
        "ignore", message=".*srun.*command is available.*",
    )
    warnings.filterwarnings(
        "ignore", message=".*fork.*",
    )

    # -- Redirect logging to prevent ghost panels ---------------------------
    # Find and temporarily mute stderr StreamHandlers.  Replace them with a
    # capture handler that feeds messages into the panel's log area.
    root_logger = logging.getLogger()
    muted_handlers: list[logging.Handler] = []
    for h in list(root_logger.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            root_logger.removeHandler(h)
            muted_handlers.append(h)

    capture = _LiveLogCapture(recent_msgs)
    root_logger.addHandler(capture)

    try:
        with Live(
            _build_display(stats, gpu, recent_msgs),
            console=console,
            refresh_per_second=refresh_per_second,
            transient=True,
        ) as live:
            for update in training_iter:
                if isinstance(update, TrainingUpdate):
                    step, loss, msg = update.step, update.loss, update.msg
                    _process_structured(update, stats)
                    if update.kind in ("fail", "warn"):
                        error_msgs.append(msg)
                else:
                    step, loss, msg = update
                    _process_tuple(step, loss, msg, stats)
                    if "[FAIL]" in msg or "[WARN]" in msg:
                        error_msgs.append(msg)

                recent_msgs.append(msg)
                if len(recent_msgs) > 20:
                    recent_msgs.pop(0)

                live.update(_build_display(stats, gpu, recent_msgs))
    finally:
        # Restore original console handlers
        root_logger.removeHandler(capture)
        for h in muted_handlers:
            root_logger.addHandler(h)

    # Print the final dashboard state (transient=True erases it on exit)
    console.print(_build_display(stats, gpu, recent_msgs))

    # Re-print errors that may have scrolled out of the log window
    for err in error_msgs:
        console.print(f"  {err}")

    stats.peak_vram_mb = gpu.peak_mb()
    return stats


def _track_plain(
    training_iter: Iterator,
    stats: TrainingStats,
    gpu: GPUMonitor,
    recent_msgs: list,
) -> TrainingStats:
    """Plain-text fallback (no Rich)."""
    for update in training_iter:
        if isinstance(update, TrainingUpdate):
            step, loss, msg = update.step, update.loss, update.msg
            _process_structured(update, stats)
        else:
            step, loss, msg = update
            _process_tuple(step, loss, msg, stats)

        print(msg)

    stats.peak_vram_mb = gpu.peak_mb()
    return stats


# ---- Update processing helpers ----------------------------------------------

def _process_structured(update: TrainingUpdate, stats: TrainingStats) -> None:
    """Extract stats from a TrainingUpdate."""
    stats.current_step = update.step
    stats.last_loss = update.loss
    stats.current_epoch = update.epoch
    if update.max_epochs > 0:
        stats.max_epochs = update.max_epochs
    if update.lr >= 0 and update.kind == "step":
        stats.last_lr = update.lr
        stats._lr_seen = True
    if update.epoch_time > 0:
        stats.last_epoch_time = update.epoch_time
    if update.steps_per_epoch > 0:
        stats.steps_per_epoch = update.steps_per_epoch

    if stats.first_loss == 0.0 and update.loss > 0:
        stats.first_loss = update.loss
    if update.loss > 0 and update.loss < stats.best_loss:
        stats.best_loss = update.loss

    if update.kind == "step":
        stats.record_step()
        stats.steps_this_session += 1

    # Track step position within the current epoch.
    # Derived from global_step so the bar stays correct even when
    # updates are sparse (log_every > 1).  At epoch boundaries
    # (kind="epoch") we show the bar as fully complete rather than
    # resetting to 0, which looked broken ("Step 0 / 3").
    if stats.steps_per_epoch > 0 and stats.current_step > 0:
        if update.kind == "epoch":
            stats.step_in_epoch = stats.steps_per_epoch  # show as complete
        else:
            stats.step_in_epoch = (
                (stats.current_step - 1) % stats.steps_per_epoch
            ) + 1

    if update.kind == "checkpoint":
        stats.checkpoints.append({
            "epoch": update.epoch,
            "loss": update.loss,
            "path": update.checkpoint_path,
        })


def _process_tuple(step: int, loss: float, msg: str, stats: TrainingStats) -> None:
    """Extract stats from a raw ``(step, loss, msg)`` tuple by parsing the msg."""
    stats.current_step = step
    stats.last_loss = loss

    if stats.first_loss == 0.0 and loss > 0:
        stats.first_loss = loss
    if loss > 0 and loss < stats.best_loss:
        stats.best_loss = loss

    msg_lower = msg.lower()
    if "epoch" in msg_lower:
        try:
            idx = msg.lower().index("epoch")
            rest = msg[idx + 5:].strip()
            parts = rest.split("/")
            if len(parts) >= 2:
                epoch_num = int(parts[0].strip())
                max_part = parts[1].split(",")[0].split(" ")[0].strip()
                max_epochs = int(max_part)
                stats.current_epoch = epoch_num
                if max_epochs > 0:
                    stats.max_epochs = max_epochs
        except (ValueError, IndexError):
            pass

    if " in " in msg and ("s," in msg or msg.rstrip().endswith("s")):
        try:
            time_part = msg.split(" in ")[1].split("s")[0].strip()
            stats.last_epoch_time = float(time_part)
        except (IndexError, ValueError):
            pass

    if msg.startswith("Epoch") and "Step" in msg and "Loss" in msg:
        stats.record_step()
        stats.steps_this_session += 1
