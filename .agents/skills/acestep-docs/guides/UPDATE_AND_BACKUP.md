# Update and Backup Guide

## Overview

All ACE-Step launch scripts check for updates on startup by default. The update check is a lightweight inline operation that runs before the application starts, ensuring you are always notified about new versions without any manual setup.

- **Default behavior**: Update checking is enabled (`CHECK_UPDATE=true`) in every launch script.
- **Platforms supported**: Windows, Linux, and macOS.
- **Graceful failures**: If git is not installed, the network is unreachable, or the project is not a git repository, the check is silently skipped and the application starts normally.
- **User control**: You can disable the check at any time by setting `CHECK_UPDATE=false`.

---

## Update Check Feature

### How It Works

Each launch script contains a lightweight inline update check that runs before the main application starts. The check does not require any external update service -- it uses git directly to compare your local commit with the remote.

**Flow:**

```text
Startup
  |
  v
CHECK_UPDATE=true?  --No--> Skip, start app
  |
  Yes
  v
Git available?  --No--> Skip, start app
  |
  Yes
  v
Valid git repo?  --No--> Skip, start app
  |
  Yes
  v
Fetch origin (10s timeout)  --Timeout/Error--> Skip, start app
  |
  Success
  v
Compare local HEAD vs origin HEAD
  |
  +-- Same commit --> "Already up to date", start app
  |
  +-- Different commit --> Show new commits, ask Y/N
        |
        +-- N --> Skip, start app
        |
        +-- Y --> Run check_update.bat / check_update.sh for full update
                    |
                    v
                  Start app
```

At every failure point (no git, no network, not a repo), the check exits gracefully and the application starts without interruption.

### Enabling and Disabling

The update check is controlled by the `CHECK_UPDATE` variable near the top of each launch script.

**Windows** (`start_gradio_ui.bat`, `start_api_server.bat`):

```batch
REM Update check on startup (set to false to disable)
set CHECK_UPDATE=true
REM set CHECK_UPDATE=false
```

**Linux / macOS** (`start_gradio_ui.sh`, `start_api_server.sh`, `start_gradio_ui_macos.sh`, `start_api_server_macos.sh`):

```bash
# Update check on startup (set to "false" to disable)
CHECK_UPDATE="true"
# CHECK_UPDATE="false"
```

To disable, change the active line to `false`. To re-enable, change it back to `true`.

### Git Requirements by Platform

The inline update check requires git to be available. How you obtain git depends on your platform.

**Windows:**

- **Option A -- PortableGit** (no installation required): Download from <https://git-scm.com/download/win>, choose the portable version, and extract to a `PortableGit\` folder in the project root. The launch scripts look for `PortableGit\bin\git.exe` first.
- **Option B -- System git**: Install git through any standard method (Git for Windows installer, winget, scoop, etc.). The launch scripts fall back to system git if PortableGit is not found.

```text
Project Root/
├── PortableGit/          <-- Optional, checked first on Windows
│   └── bin/
│       └── git.exe
├── start_gradio_ui.bat
├── check_update.bat
└── ...
```

**Linux:**

Install git through your distribution's package manager:

```bash
# Ubuntu / Debian
sudo apt install git

# CentOS / RHEL / Fedora
sudo yum install git
# or
sudo dnf install git

# Arch Linux
sudo pacman -S git
```

**macOS:**

Install git through Xcode command-line tools or Homebrew:

```bash
# Xcode command-line tools (includes git)
xcode-select --install

# Or via Homebrew
brew install git
```

### Example Output

**Already up to date:**

```text
[Update] Checking for updates...
[Update] Already up to date (abc1234).

Starting ACE-Step Gradio Web UI...
```

**Update available:**

```text
[Update] Checking for updates...

========================================
  Update available!
========================================
  Current: abc1234  ->  Latest: def5678

  Recent changes:
* def5678 Fix audio processing bug
* ccc3333 Add new model support

Update now before starting? (Y/N):
```

If you choose **Y**, the script delegates to `check_update.bat` (Windows) or `check_update.sh` (Linux/macOS) for the full update process including backup handling. If you choose **N**, the update is skipped and the application starts with the current version.

**Network unreachable (auto-skip):**

```text
[Update] Checking for updates...
[Update] Network unreachable, skipping.

Starting ACE-Step Gradio Web UI...
```

---

## Manual Update

You can run the update check manually at any time, outside of the launch scripts.

**Windows:**

```batch
check_update.bat
```

**Linux / macOS:**

```bash
./check_update.sh
```

The manual update scripts perform the same 4-step process:

1. Detect git and verify the repository
2. Fetch from origin with a 10-second timeout
3. Compare local and remote commits
4. If an update is available, prompt to apply it (with automatic backup of conflicting files)

---

## File Backup During Updates

### Automatic Backup

When you choose to update and you have locally modified files that also changed on the remote, ACE-Step automatically creates a backup before applying the update.

**Supported file types** (any modified text file is backed up):

- Configuration files: `.bat`, `.sh`, `.yaml`, `.json`, `.ini`
- Python code: `.py`
- Documentation: `.md`, `.txt`

### Backup Process

```text
1. Update detects locally modified files
   that also changed on the remote
   |
   v
2. Creates a timestamped backup directory
   .update_backup_YYYYMMDD_HHMMSS/
   |
   v
3. Copies conflicting files into the backup
   (preserves directory structure)
   |
   v
4. Resets working tree to the remote version
   |
   v
5. Displays backup location and instructions
```

### Example

**Your local modifications:**

- `start_gradio_ui.bat` -- Changed language to Chinese
- `acestep/handler.py` -- Added debug logging
- `config.yaml` -- Changed model path

**Remote updates:**

- `start_gradio_ui.bat` -- Added new features
- `acestep/handler.py` -- Bug fixes
- `config.yaml` -- New parameters

**Backup created:**

```text
.update_backup_20260205_143022/
├── start_gradio_ui.bat          (your version)
├── config.yaml                  (your version)
└── acestep/
    └── handler.py               (your version)
```

**Working tree after update:**

```text
start_gradio_ui.bat              (new version from GitHub)
config.yaml                      (new version from GitHub)
acestep/
└── handler.py                   (new version from GitHub)
```

Your original files are preserved in the backup directory so you can merge your changes back in.

---

## Merging Configurations

After an update that backed up your files, use the merge helper to compare and restore your settings.

### Windows: merge_config.bat

```batch
merge_config.bat
```

When comparing files, this script opens two Notepad windows side by side -- one with the backup version and one with the current version -- so you can manually copy your settings across.

### Linux / macOS: merge_config.sh

```bash
./merge_config.sh
```

When comparing files, this script uses `colordiff` (if installed) or `diff` to display a unified diff in the terminal, showing exactly what changed between your backed-up version and the new version.

To install colordiff for colored output:

```bash
# Ubuntu / Debian
sudo apt install colordiff

# macOS (Homebrew)
brew install colordiff

# Arch Linux
sudo pacman -S colordiff
```

### Menu Options (Both Platforms)

Both `merge_config.bat` and `merge_config.sh` present the same interactive menu:

```text
========================================
ACE-Step Backup Merge Helper
========================================

1. Compare backup with current files
2. Restore a file from backup
3. List all backed up files
4. Delete old backups
5. Exit
```

| Option | Description |
|--------|-------------|
| **1. Compare** | Show differences between your backup and the current (updated) file. On Windows this opens two Notepad windows. On Linux/macOS this prints a unified diff to the terminal. |
| **2. Restore** | Copy a file from the backup back into the project, overwriting the updated version. Use this only if the new version causes problems. |
| **3. List** | Display all files stored in backup directories. |
| **4. Delete** | Permanently remove old backup directories. Only do this after you have finished merging. |

### Merging Common Files

**Launch scripts** (`start_gradio_ui.bat`, `start_gradio_ui.sh`, etc.):

Look for your custom settings in the backup (language, port, download source, etc.) and copy them into the corresponding lines of the new version.

```bash
# Example settings you may want to preserve:
LANGUAGE="zh"
PORT=8080
DOWNLOAD_SOURCE="--download-source modelscope"
```

**Configuration files** (`config.yaml`, `.json`):

Compare the structures. Keep your custom values, add any new keys from the updated version.

```yaml
# Backup (your version)
model_path: "custom/path"
custom_setting: true

# Current (new version)
model_path: "default/path"
new_feature: enabled

# Merged result
model_path: "custom/path"       # Keep your setting
custom_setting: true             # Keep your setting
new_feature: enabled             # Add new feature
```

---

## Testing Update Functionality

Use the test scripts to verify that your git setup and update mechanism are working correctly before relying on them.

**Windows:**

```batch
test_git_update.bat
```

**Linux / macOS:**

```bash
./test_git_update.sh
```

### What the Tests Check

1. **Git availability**: Verifies that git can be found (PortableGit or system git on Windows; system git on Linux/macOS).
2. **Repository validity**: Confirms the project directory is a valid git repository.
3. **Update script presence**: Checks that `check_update.bat` / `check_update.sh` exists.
4. **Network connectivity**: Attempts an actual fetch from the remote (with timeout).

### Example Test Output

```text
========================================
Test Git Update Check
========================================

[Test 1] Checking Git...
[PASS] Git found
git version 2.43.0

[Test 2] Checking git repository...
[PASS] Valid git repository
  Branch: main
  Commit: a1b2c3d

[Test 3] Checking update script...
[PASS] check_update.sh found

[Test 4] Running update check...
[PASS] Update check completed successfully

[PASS] All tests completed
```

---

## Troubleshooting

### Git not found

The update check is silently skipped if git is not available. To enable it, install git for your platform:

| Platform | Install Command |
|----------|----------------|
| **Windows (PortableGit)** | Download from <https://git-scm.com/download/win> and extract to `PortableGit\` in the project root |
| **Windows (system)** | `winget install --id Git.Git -e` or use the Git for Windows installer |
| **Ubuntu / Debian** | `sudo apt install git` |
| **CentOS / RHEL** | `sudo yum install git` |
| **Arch Linux** | `sudo pacman -S git` |
| **macOS** | `xcode-select --install` or `brew install git` |

### Network timeout

The fetch operation has a 10-second timeout. If it times out, the update check is skipped automatically and the application starts normally. This is expected behavior on slow or restricted networks.

On macOS, the timeout mechanism uses `gtimeout` from GNU coreutils if available, or falls back to a plain fetch without a timeout. To get proper timeout support:

```bash
brew install coreutils
```

### Proxy configuration

**Windows (`check_update.bat`):**

Create a `proxy_config.txt` file in the project root:

```text
PROXY_ENABLED=1
PROXY_URL=http://127.0.0.1:7890
```

Or configure interactively:

```batch
check_update.bat proxy
```

Common proxy formats:

| Type | Example |
|------|---------|
| HTTP proxy | `http://127.0.0.1:7890` |
| HTTPS proxy | `https://proxy.company.com:8080` |
| SOCKS5 proxy | `socks5://127.0.0.1:1080` |

To disable the proxy, set `PROXY_ENABLED=0` in `proxy_config.txt`.

**Linux / macOS:**

Set standard environment variables before running the script:

```bash
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
./check_update.sh
```

Or add them to your shell profile (`~/.bashrc`, `~/.zshrc`) for persistence.

### Merge conflicts

If the automatic update fails or produces unexpected results:

1. Check for backup directories: look for `.update_backup_*` folders in the project root.
2. Use the merge helper (`merge_config.bat` or `./merge_config.sh`) to compare and restore files.
3. If needed, manually inspect the diff between your backup and the current files.

### Lost configuration after update

1. Find your backup:
   - **Windows:** `dir /b .update_backup_*`
   - **Linux / macOS:** `ls -d .update_backup_*`
2. Use the merge helper (Option 2) to restore specific files, or manually copy settings from the backup.

---

## Quick Reference

| Action | Windows | Linux / macOS |
|--------|---------|---------------|
| **Enable update check** | `set CHECK_UPDATE=true` (in `.bat`) | `CHECK_UPDATE="true"` (in `.sh`) |
| **Disable update check** | `set CHECK_UPDATE=false` (in `.bat`) | `CHECK_UPDATE="false"` (in `.sh`) |
| **Manual update** | `check_update.bat` | `./check_update.sh` |
| **Configure proxy** | `check_update.bat proxy` or edit `proxy_config.txt` | `export http_proxy=... && ./check_update.sh` |
| **Merge configurations** | `merge_config.bat` | `./merge_config.sh` |
| **Test update setup** | `test_git_update.bat` | `./test_git_update.sh` |
| **List backups** | `dir /b .update_backup_*` | `ls -d .update_backup_*` |
| **Delete a backup** | `rmdir /s /q .update_backup_YYYYMMDD_HHMMSS` | `rm -rf .update_backup_YYYYMMDD_HHMMSS` |
