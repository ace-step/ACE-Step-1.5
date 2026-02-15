"""
Post-training summary panel.

Displays final statistics after training completes: total time, loss
trajectory, GPU usage, saved checkpoints grid, output paths, and
next-steps hints.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from acestep.training_v2.ui import console, is_rich_active
from acestep.training_v2.ui.progress import TrainingStats


def _dir_size_str(path: str) -> str:
    """Return human-readable size of a directory."""
    try:
        total = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
        if total > 1024 ** 3:
            return f"{total / 1024 ** 3:.2f} GiB"
        if total > 1024 ** 2:
            return f"{total / 1024 ** 2:.1f} MiB"
        if total > 1024:
            return f"{total / 1024:.0f} KiB"
        return f"{total} B"
    except Exception:
        return "unknown"


def show_summary(
    stats: TrainingStats,
    output_dir: str,
    log_dir: Optional[str] = None,
) -> None:
    """Display the post-training summary.

    If training completed 0 steps, shows a failure panel with diagnostics
    instead of a misleading "Training Complete" message.

    Args:
        stats: Accumulated training statistics from the progress tracker.
        output_dir: Path to the LoRA output directory.
        log_dir: Path to TensorBoard log directory (for the hint).
    """
    if stats.current_step == 0 and stats.current_epoch == 0:
        _show_failure(stats, output_dir)
        return

    if is_rich_active() and console is not None:
        _show_rich(stats, output_dir, log_dir)
    else:
        _show_plain(stats, output_dir, log_dir)


def _show_failure(stats: TrainingStats, output_dir: str) -> None:
    """Show a clear failure message when training completes with 0 steps."""
    if is_rich_active() and console is not None:
        from rich.panel import Panel

        console.print(
            Panel(
                "[bold red]Training did not run.[/]\n\n"
                "  0 epochs completed, 0 steps executed.\n\n"
                "  Common causes:\n"
                "  1. [bold]Dataset directory is empty[/] -- no .pt files found\n"
                "  2. [bold]Device mismatch[/] -- wrong GPU index or insufficient VRAM\n"
                "  3. [bold]Dependency issue[/] -- peft, lightning, or bitsandbytes\n\n"
                "  Check [bold]sidestep.log[/] for the full error traceback.",
                title="[bold red]Training Failed[/]",
                border_style="red",
                padding=(0, 1),
            )
        )
    else:
        print("\n" + "=" * 60, file=sys.stderr)
        print("  TRAINING FAILED -- 0 steps executed", file=sys.stderr)
        print("  Check sidestep.log for the full error traceback.", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)


def _show_rich(
    stats: TrainingStats,
    output_dir: str,
    log_dir: Optional[str],
) -> None:
    """Rich summary panel with 2-column checkpoint grid."""
    from rich.columns import Columns
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    assert console is not None

    # -- Stats table ----------------------------------------------------------
    table = Table(
        show_header=False, show_edge=False, box=None,
        pad_edge=True, expand=False,
    )
    table.add_column("key", style="dim", min_width=20)
    table.add_column("val", min_width=30)

    table.add_row("Total time", f"[bold]{stats.elapsed_str}[/]")
    table.add_row("Epochs completed", f"{stats.current_epoch} / {stats.max_epochs}")
    table.add_row("Total steps", str(stats.current_step))

    if stats.first_loss > 0:
        direction = "down" if stats.last_loss < stats.first_loss else "up"
        color = "green" if direction == "down" else "red"
        pct = abs(stats.last_loss - stats.first_loss) / stats.first_loss * 100
        table.add_row(
            "Loss",
            f"[bold]{stats.first_loss:.4f}[/] -> [{color}]{stats.last_loss:.4f}[/]  "
            f"[dim]({direction} {pct:.1f}%)[/]",
        )
    if stats.best_loss < float("inf"):
        table.add_row("Best loss", f"[green]{stats.best_loss:.4f}[/]")
    if stats.peak_vram_mb > 0:
        table.add_row("Peak VRAM", f"{stats.peak_vram_mb / 1024:.1f} GiB")
    if stats.samples_per_sec > 0:
        table.add_row("Avg speed", f"{stats.samples_per_sec:.1f} steps/s")

    # -- Saved checkpoints grid (2-column) ------------------------------------
    ckpt_section = _build_checkpoint_grid(stats, output_dir)

    # -- Output paths ---------------------------------------------------------
    paths = Table(
        show_header=False, show_edge=False, box=None,
        pad_edge=True, expand=False,
    )
    paths.add_column("key", style="dim", min_width=20)
    paths.add_column("val", min_width=30)

    final_dir = Path(output_dir) / "final"
    paths.add_row("Output dir", str(output_dir))
    if final_dir.exists():
        paths.add_row(
            "Final weights",
            f"{final_dir}  [dim]({_dir_size_str(str(final_dir))})[/]",
        )
    if log_dir:
        paths.add_row("TensorBoard", str(log_dir))

    # -- Next steps -----------------------------------------------------------
    hints = Text()
    hints.append("\n  Next steps:\n", style="bold")
    hints.append("  1. Use the adapter:  ", style="dim")
    hints.append(f"load from {final_dir}\n")
    if log_dir:
        hints.append("  2. View metrics:  ", style="dim")
        hints.append(f"tensorboard --logdir {log_dir}\n")
    hints.append("  3. Generate music with the adapter via the Gradio UI\n", style="dim")

    # -- Assemble panel -------------------------------------------------------
    parts = [table, Text("")]
    if ckpt_section is not None:
        parts.extend([ckpt_section, Text("")])
    parts.extend([paths, hints])

    console.print(
        Panel(
            Group(*parts),
            title="[bold green]Training Complete[/]",
            border_style="green",
            padding=(0, 1),
        )
    )


def _build_checkpoint_grid(
    stats: TrainingStats, output_dir: str,
) -> Optional[Any]:
    """Build a 2-column grid of saved checkpoints, or None if there are none."""
    from rich.table import Table
    from rich.text import Text

    if not stats.checkpoints:
        return None

    header = Text("  Saved Checkpoints", style="bold")

    grid = Table(
        show_header=True, show_edge=False, box=None,
        pad_edge=True, expand=True,
    )
    grid.add_column("Epoch", style="bold cyan", justify="right", min_width=8)
    grid.add_column("Loss", min_width=10)
    grid.add_column("Epoch", style="bold cyan", justify="right", min_width=8)
    grid.add_column("Loss", min_width=10)

    # Pair checkpoints into rows of 2
    ckpts = stats.checkpoints
    for i in range(0, len(ckpts), 2):
        c1 = ckpts[i]
        loss1 = f"{c1['loss']:.4f}" if c1["loss"] > 0 else "--"
        if i + 1 < len(ckpts):
            c2 = ckpts[i + 1]
            loss2 = f"{c2['loss']:.4f}" if c2["loss"] > 0 else "--"
            grid.add_row(
                str(c1["epoch"]), loss1,
                str(c2["epoch"]), loss2,
            )
        else:
            grid.add_row(str(c1["epoch"]), loss1, "", "")

    from rich.console import Group
    return Group(header, grid)


def _show_plain(
    stats: TrainingStats,
    output_dir: str,
    log_dir: Optional[str],
) -> None:
    """Plain-text fallback summary."""
    print("\n" + "=" * 60, file=sys.stderr)
    print("  Training Complete", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  Total time .......... {stats.elapsed_str}", file=sys.stderr)
    print(f"  Epochs .............. {stats.current_epoch} / {stats.max_epochs}", file=sys.stderr)
    print(f"  Total steps ......... {stats.current_step}", file=sys.stderr)

    if stats.first_loss > 0:
        print(f"  Loss ................ {stats.first_loss:.4f} -> {stats.last_loss:.4f}", file=sys.stderr)
    if stats.best_loss < float("inf"):
        print(f"  Best loss ........... {stats.best_loss:.4f}", file=sys.stderr)
    if stats.peak_vram_mb > 0:
        print(f"  Peak VRAM ........... {stats.peak_vram_mb / 1024:.1f} GiB", file=sys.stderr)

    # Checkpoints
    if stats.checkpoints:
        print("\n  Saved Checkpoints:", file=sys.stderr)
        for c in stats.checkpoints:
            loss_s = f"{c['loss']:.4f}" if c["loss"] > 0 else "--"
            print(f"    Epoch {c['epoch']:>4}  Loss: {loss_s}", file=sys.stderr)

    print(f"\n  Output dir .......... {output_dir}", file=sys.stderr)
    final_dir = Path(output_dir) / "final"
    if final_dir.exists():
        print(f"  Final weights ....... {final_dir}  ({_dir_size_str(str(final_dir))})", file=sys.stderr)
    if log_dir:
        print(f"  TensorBoard ......... {log_dir}", file=sys.stderr)

    print("=" * 60 + "\n", file=sys.stderr)
