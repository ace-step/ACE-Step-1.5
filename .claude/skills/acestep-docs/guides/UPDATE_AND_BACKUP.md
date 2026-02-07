# Update and Backup Guide

**For Portable Package Users**

This guide is specifically designed for **Windows portable package users** who want to keep their ACE-Step installation up-to-date using Git. If you downloaded the portable package (ACE-Step-1.5.7z), this guide will help you set up automatic update checks and handle configuration conflicts during updates.

> **Note**: If you're using the Git repository with `uv`, you can simply use `git pull` directly. This guide focuses on portable package users who need PortableGit for updates.

---

## Git Update Check Feature

### Overview

Portable package users can use PortableGit to automatically check for updates from GitHub without needing a full Git installation.

### Requirements

1. **PortableGit**: Download from https://git-scm.com/download/win
   - Extract to `PortableGit\` folder in project root
   - File location: `PortableGit\bin\git.exe`

2. **Git Repository**: Project must be a valid Git repository

3. **Internet Connection**: Required to check GitHub

### Setup

**1. Install PortableGit**
```
Project Root/
├── PortableGit/
│   └── bin/
│       └── git.exe
├── start_gradio_ui.bat
└── ...
```

**2. Enable Update Check**

Edit `start_gradio_ui.bat` or `start_api_server.bat`:
```batch
REM Update check: true or false
set CHECK_UPDATE=true
```

**3. Run Startup Script**
```batch
start_gradio_ui.bat
```

### Update Flow

```
1. Startup script runs
   ↓
2. Checks if CHECK_UPDATE=true
   ↓
3. Connects to GitHub (10 second timeout)
   ↓
4. Compares local vs remote version
   ↓
5a. Up to date → Continue startup
5b. Update available → Prompt user
5c. Timeout/error → Skip check, continue startup
```

### Example Output

**Already up to date**:
```
========================================
ACE-Step Update Check
========================================

[1/4] Checking current version...
  Branch: main
  Commit: a1b2c3d

[2/4] Checking for updates (timeout: 10s)...
  [Success] Fetched latest information from GitHub.

[3/4] Comparing versions...
  Local:  a1b2c3d
  Remote: a1b2c3d

[4/4] Result: Already up to date!

Starting ACE-Step Gradio Web UI...
```

**Update available**:
```
[4/4] Result: Update available!
  A new version is available on GitHub.

  New commits:
  * e4f5g6h Fix audio processing bug
  * c3d4e5f Add new model support

Do you want to update now? (Y/N):
```

**Network timeout (auto-skip)**:
```
[2/4] Checking for updates (timeout: 10s)...
  [Timeout] Could not connect to GitHub within 10 seconds.
  Skipping update check.

Continuing with startup...
```

---

## File Backup During Updates

### Automatic Backup

When updating, if you modified files that were also updated remotely, ACE-Step automatically creates a backup.

**Supported file types**:
- Configuration files: `.bat`, `.yaml`, `.json`, `.ini`
- Python code: `.py`
- Documentation: `.md`, `.txt`
- Any modified text files

### Backup Process

```
1. Update check detects conflicts
   (Local modified + Remote modified)
   ↓
2. Creates backup directory
   .update_backup_YYYYMMDD_HHMMSS/
   ↓
3. Backs up conflicting files
   (Preserves directory structure)
   ↓
4. Restores files to remote version
   ↓
5. Executes git pull
   ↓
6. Shows backup location
```

### Example Backup

**Your modifications**:
- `start_gradio_ui.bat` - Changed language to Chinese
- `acestep/handler.py` - Added debug logging
- `config.yaml` - Changed model path

**Remote updates**:
- `start_gradio_ui.bat` - Added new features
- `acestep/handler.py` - Bug fixes
- `config.yaml` - New parameters

**Backup created**:
```
.update_backup_20260205_143022/
├── start_gradio_ui.bat      (your version)
├── config.yaml              (your version)
└── acestep/
    └── handler.py           (your version)
```

**Current files** (after update):
```
start_gradio_ui.bat      (new version from GitHub)
config.yaml              (new version from GitHub)
acestep/
└── handler.py           (new version from GitHub)
```

---

## Merging Configurations

### Using merge_config.bat

Run the merge helper script:
```batch
merge_config.bat
```

**Menu Options**:

```
========================================
ACE-Step Backup Merge Helper
========================================

1. Compare backup with current files
2. Restore a file from backup
3. List all backed up files
4. Delete old backups
5. Exit
```

### Option 1: Compare Files

**Best for**: Manually merging changes

**Steps**:
1. Select backup directory
2. Enter filename (e.g., `start_gradio_ui.bat` or `acestep\handler.py`)
3. Two Notepad windows open side-by-side
4. Copy your settings from backup to new version

**Example**:
```
Files in backup:
  - start_gradio_ui.bat
  - config.yaml
  - acestep\handler.py

Enter filename to compare: start_gradio_ui.bat

Opening files for comparison...
Backup:  .update_backup_20260205_143022\start_gradio_ui.bat
Current: start_gradio_ui.bat
```

### Option 2: Restore File

**Best for**: Completely reverting to your version

**Warning**: Overwrites current file, loses GitHub updates

**Use only if**: New version has issues or you need old settings

### Option 3: List Files

**Shows**: All backed up files with directory structure

### Option 4: Delete Backups

**Warning**: Permanent deletion

**Only use after**: Successfully merging all configurations

---

## Merging Common Files

### start_gradio_ui.bat

**Your settings to preserve**:
```batch
set LANGUAGE=zh              # Your language preference
set DOWNLOAD_SOURCE=--download-source modelscope  # Your download source
set PORT=8080                # Your custom port
```

**How to merge**:
1. Open both versions (Option 1 in merge_config.bat)
2. Find your custom settings in backup
3. Copy them to the new version
4. Save new version

### Python Files

**Example**: `acestep/handler.py`

**Your changes**:
```python
# Added debug logging
logger.setLevel(logging.DEBUG)
```

**New version changes**:
```python
# Bug fix for audio processing
def process_audio(file):
    # ... new implementation
```

**Merge**:
1. Identify your changes in backup
2. Identify new changes in current version
3. Manually combine both changes
4. Test functionality

### Configuration Files (YAML/JSON)

**Example**: `config.yaml`

**Compare structure**:
```yaml
# Backup (your version)
model_path: "custom/path"
custom_setting: true

# Current (new version)
model_path: "default/path"
new_feature: enabled
```

**Merge**:
```yaml
# Final version
model_path: "custom/path"      # Keep your setting
custom_setting: true            # Keep your setting
new_feature: enabled            # Add new feature
```

---

## Best Practices

### Before Updating

1. **Note your changes**:
   ```batch
   REM Remember what you modified:
   REM - Changed LANGUAGE to zh
   REM - Changed PORT to 8080
   REM - Set DOWNLOAD_SOURCE to modelscope
   ```

2. **Backup important files manually** (optional):
   ```batch
   copy start_gradio_ui.bat my_config_backup.bat
   ```

### After Updating

1. **Check backup directory**:
   ```batch
   dir /b .update_backup_*
   ```

2. **Review each file** using merge_config.bat

3. **Test application** after merging

4. **Delete backups** after confirming everything works

### If Update Fails

**Rollback to previous version**:
```batch
cd PortableGit\bin
git log --oneline
# Note the commit hash before update

# Rollback
git reset --hard <commit-hash>
```

---

## Troubleshooting

### PortableGit not found

**Solution**: Download and extract to `PortableGit\` folder
- https://git-scm.com/download/win
- Choose "Portable" version

### Update check timeout

**Normal behavior**: Automatically skips after 10 seconds

**To disable**:
```batch
set CHECK_UPDATE=false
```

### Network issues / Cannot access GitHub

**If you're behind a firewall or need to use a proxy**, configure proxy using `proxy_config.txt`:

**Method 1: Create proxy_config.txt (Recommended)**

Create a file named `proxy_config.txt` in the project root directory with the following content:

```
PROXY_ENABLED=1
PROXY_URL=http://127.0.0.1:7890
```

**Common proxy examples:**

1. **V2Ray/Clash (Local SOCKS5)**:
   ```
   PROXY_ENABLED=1
   PROXY_URL=socks5://127.0.0.1:1080
   ```

2. **Corporate HTTP Proxy**:
   ```
   PROXY_ENABLED=1
   PROXY_URL=http://proxy.company.com:8080
   ```

3. **HTTP Proxy with port**:
   ```
   PROXY_ENABLED=1
   PROXY_URL=http://127.0.0.1:7890
   ```

**To disable proxy:**
```
PROXY_ENABLED=0
PROXY_URL=
```

**Method 2: Run check_update.bat with proxy argument**

```batch
# Configure proxy interactively
check_update.bat proxy

# Follow the prompts to enter proxy URL
# Examples shown:
#   - HTTP proxy:  http://127.0.0.1:7890
#   - HTTPS proxy: https://proxy.example.com:8080
#   - SOCKS5:      socks5://127.0.0.1:1080
```

**Verify proxy configuration:**

After setting up proxy, run update check to test:
```batch
check_update.bat
```

You should see:
```
[Proxy] Using proxy server: http://127.0.0.1:7890
```

**Alternative**: If proxy doesn't work, disable update check:
```batch
set CHECK_UPDATE=false
```

### Merge conflicts

**Solution**: Use merge_config.bat Option 1 to compare files manually

### Lost configuration

**Solution**:
1. Find backup: `dir /b .update_backup_*`
2. Use merge_config.bat Option 2 to restore
3. Or manually copy settings from backup

---

## Quick Reference

**Enable updates**:
```batch
set CHECK_UPDATE=true
```

**Manual update check**:
```batch
check_update.bat
```

**Configure proxy**:
```batch
check_update.bat proxy
```

**Test update functionality**:
```batch
test_git_update.bat
```

**Merge configurations**:
```batch
merge_config.bat
```

**List backups**:
```batch
dir /b .update_backup_*
```

**Delete old backups**:
```batch
rmdir /s /q .update_backup_YYYYMMDD_HHMMSS
```

---

## Testing Update Functionality

Use `test_git_update.bat` to verify your update setup before using it.

### Running the Test

```batch
test_git_update.bat
```

### Test Output Example

```
========================================
Test Git Update Check
========================================

[Test 1] Checking PortableGit...
[PASS] PortableGit found
git version 2.43.0.windows.1

[Test 2] Checking git repository...
[PASS] Valid git repository
  Branch: main
  Commit: a1b2c3d

[Test 3] Checking check_update.bat...
[PASS] check_update.bat found

[Test 4] Running update check...
[PASS] Update check completed successfully

[PASS] All tests completed
```

### What the Test Checks

1. **PortableGit Installation**: Verifies `PortableGit\bin\git.exe` exists
2. **Git Repository**: Confirms project is a valid Git repository
3. **Update Script**: Checks `check_update.bat` exists
4. **Network Connectivity**: Attempts actual update check (with timeout)

### If Test Fails

**Test 1 Failed** - PortableGit not found:
- Download from https://git-scm.com/download/win
- Extract to `PortableGit\` folder

**Test 2 Failed** - Not a git repository:
- Use Git repository version instead of portable package
- Or initialize Git: See "Setup" section above

**Test 4 Failed** - Network timeout:
- Configure proxy: See "Network issues" section above
- Or acceptable if GitHub is not accessible (update will skip automatically)
