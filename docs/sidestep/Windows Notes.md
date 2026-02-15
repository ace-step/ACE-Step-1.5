# Windows Notes

Side-Step fully supports Windows with CUDA GPUs. This page documents Windows-specific behavior, workarounds, and configuration details that differ from Linux/macOS.

---

## Installation

The easiest way to install on Windows is the **Easy Installer**:

1. Clone or download Side-Step.
2. Double-click `install_windows.bat` (or run `install_windows.ps1` from PowerShell).

The installer handles everything:

- Installs `uv` (if not already present)
- Installs Python 3.11
- Clones ACE-Step 1.5 alongside Side-Step
- Runs `uv sync` for all dependencies
- Optionally downloads model checkpoints

**Requirements:** Windows 10/11, PowerShell 5.1+, Git, NVIDIA GPU with CUDA drivers.

The installer creates two sibling directories:

```
Parent/
├── Side-Step/       <-- Your training toolkit
└── ACE-Step-1.5/    <-- Model checkpoints + optional vanilla mode
```

### Running from PowerShell

```powershell
cd Side-Step
uv run train.py
```

Both PowerShell and CMD work. The wizard displays Windows-native paths (backslashes) in its prompts.

---

## DataLoader Workers (num_workers = 0)

**On Windows, Side-Step forces `num_workers=0` regardless of what you set.**

This is because Windows uses spawn-based multiprocessing (rather than fork), which breaks PyTorch's DataLoader workers. Attempting to use workers > 0 on Windows causes crashes or hangs.

Side-Step handles this automatically:

- The CLI default is `0` on Windows.
- The wizard warns you and clamps to `0` if you enter a higher value.
- The trainer enforces `0` at runtime even if overridden via CLI.

When `num_workers=0`:

- `prefetch_factor` is forced to `0` (no background prefetching).
- `persistent_workers` is forced to `False`.

**Impact:** Data loading is slightly slower (single-threaded), but training speed is dominated by GPU computation, so the difference is usually negligible.

---

## Multi-GPU Device Selection

On Windows, Lightning Fabric's `devices=[index]` parameter causes `DistributedSampler` to produce 0 batches, which makes training silently "complete" with 0 steps.

Side-Step works around this by using `devices=1` and calling `torch.cuda.set_device(device_idx)` directly. This means multi-GPU selection (e.g., `--device cuda:1`) works correctly on Windows.

---

## Configuration and Preset Paths

Side-Step stores user configuration and presets at Windows-standard locations:

| Item | Path |
| :--- | :--- |
| Settings | `%APPDATA%\sidestep\settings.json` |
| Global presets | `%APPDATA%\sidestep\presets\` |
| Local presets | `.\presets\` (in the Side-Step project directory) |

`%APPDATA%` typically resolves to `C:\Users\<you>\AppData\Roaming`.

Local presets take priority over global presets. See [[Preset Management]] for details.

---

## Log File

Side-Step writes a log file (`sidestep.log`) to the current working directory. On some Windows setups (e.g., running from a read-only directory or a restricted location), the log file may fail to create. In that case, Side-Step falls back to console-only logging with no error.

If you need the log file for troubleshooting, make sure you run Side-Step from a writable directory (e.g., the Side-Step project folder itself).

---

## Preset Name Safety

Preset names are validated against Windows reserved filenames. The following names are rejected:

`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`

Characters `/\:*?"<>|` are also stripped from preset names. This validation applies on all platforms, not just Windows, to keep presets portable.

---

## Path Length (MAX_PATH)

Windows has a historical 260-character path length limit (MAX_PATH). Side-Step does not explicitly handle this. If you encounter path-related errors:

- Keep your project close to the drive root (e.g., `C:\ai\Side-Step\` rather than deeply nested directories).
- Avoid very long output directory names.
- Consider enabling long paths in Windows: Settings > System > For Developers > Enable long paths. This requires Windows 10 version 1607 or later.

---

## Summary of Windows-Specific Behavior

| Behavior | What Happens | Why |
| :--- | :--- | :--- |
| `num_workers` clamped to `0` | DataLoader runs single-threaded | Windows spawn-based multiprocessing breaks PyTorch workers |
| `prefetch_factor` forced to `0` | No background batch prefetching | Required when `num_workers=0` |
| `persistent_workers` forced off | Workers not kept alive between epochs | Required when `num_workers=0` |
| Fabric `devices=1` | Uses `torch.cuda.set_device()` instead of device list | `devices=[index]` causes 0-batch bug on Windows |
| Backslash paths in prompts | Path display uses `\` separator | Native Windows path convention |
| Config stored in `%APPDATA%` | Settings and global presets in AppData | Windows standard user config location |
| File explorer uses `explorer` | "Open folder" actions use Windows Explorer | Platform-appropriate file manager |

---

## See Also

- [[Getting Started]] -- Installation and first-run setup
- [[Preset Management]] -- Preset storage and management
- [[VRAM Optimization Guide]] -- GPU memory profiles
