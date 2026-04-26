#!/usr/bin/env bash
# Git Update Check Utility - Linux/macOS
# This script checks for updates from GitHub and optionally updates the repository

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
TIMEOUT_SECONDS=10
GIT_PATH=""
REPO_PATH="$SCRIPT_DIR"

echo "========================================"
echo "ACE-Step Update Check"
echo "========================================"
echo

# Find git
if command -v git &>/dev/null; then
    GIT_PATH="$(command -v git)"
    echo "[Git] Using system Git: $GIT_PATH"
else
    echo "[Error] Git not found."
    echo
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "Please install Git:"
        echo "  xcode-select --install"
        echo "  or: brew install git"
    else
        echo "Please install Git:"
        echo "  Ubuntu/Debian: sudo apt install git"
        echo "  CentOS/RHEL:   sudo yum install git"
        echo "  Arch:          sudo pacman -S git"
    fi
    echo
    exit 1
fi
echo

# Check if this is a git repository
cd "$REPO_PATH"
if ! "$GIT_PATH" rev-parse --git-dir &>/dev/null; then
    echo "[Error] Not a git repository."
    echo "This folder does not appear to be a git repository."
    echo
    exit 1
fi

echo "[1/4] Checking current version..."
CURRENT_BRANCH="$("$GIT_PATH" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")"
CURRENT_COMMIT="$("$GIT_PATH" rev-parse --short HEAD 2>/dev/null || echo "unknown")"

echo "  Branch: $CURRENT_BRANCH"
echo "  Commit: $CURRENT_COMMIT"
echo

echo "[2/4] Checking for updates (timeout: ${TIMEOUT_SECONDS}s)..."
echo "  Connecting to GitHub..."

# Fetch remote with timeout
FETCH_SUCCESS=0
if timeout "$TIMEOUT_SECONDS" "$GIT_PATH" fetch origin --quiet 2>/dev/null; then
    FETCH_SUCCESS=1
elif command -v gtimeout &>/dev/null; then
    # macOS with coreutils installed via brew
    if gtimeout "$TIMEOUT_SECONDS" "$GIT_PATH" fetch origin --quiet 2>/dev/null; then
        FETCH_SUCCESS=1
    fi
else
    # Fallback: try without timeout (macOS without coreutils)
    if "$GIT_PATH" fetch origin --quiet 2>/dev/null; then
        FETCH_SUCCESS=1
    fi
fi

if [[ $FETCH_SUCCESS -eq 0 ]]; then
    echo "  [Failed] Could not fetch from GitHub."
    echo "  Please check your internet connection."
    echo
    exit 2
fi

echo "  [Success] Fetched latest information from GitHub."
echo

echo "[3/4] Comparing versions..."
REMOTE_COMMIT="$("$GIT_PATH" rev-parse --short "origin/$CURRENT_BRANCH" 2>/dev/null || echo "")"

if [[ -z "$REMOTE_COMMIT" ]]; then
    echo "  [Warning] Remote branch 'origin/$CURRENT_BRANCH' not found."
    echo
    echo "  Checking main branch instead..."
    FALLBACK_BRANCH="main"
    REMOTE_COMMIT="$("$GIT_PATH" rev-parse --short "origin/$FALLBACK_BRANCH" 2>/dev/null || echo "")"

    if [[ -z "$REMOTE_COMMIT" ]]; then
        echo "  [Error] Could not find remote main branch either."
        exit 1
    fi

    echo "  Found main branch: $REMOTE_COMMIT"
    echo

    read -rp "  Switch to main branch? (Y/N): " SWITCH_BRANCH
    if [[ "$SWITCH_BRANCH" == "Y" || "$SWITCH_BRANCH" == "y" ]]; then
        echo
        echo "  Switching to main branch..."
        if "$GIT_PATH" checkout main; then
            echo "  [Success] Switched to main branch."
            echo "  Please run this script again to check for updates."
            exit 0
        else
            echo "  [Error] Failed to switch branch."
            exit 1
        fi
    else
        echo
        echo "  Staying on branch '$CURRENT_BRANCH'. No update performed."
        exit 0
    fi
fi

echo "  Local:  $CURRENT_COMMIT"
echo "  Remote: $REMOTE_COMMIT"
echo

# Compare commits
if [[ "$CURRENT_COMMIT" == "$REMOTE_COMMIT" ]]; then
    echo "[4/4] Result: Already up to date!"
    echo "  You have the latest version."
    echo
    exit 0
fi

echo "[4/4] Result: Update available!"

# Check if local is behind remote
if "$GIT_PATH" merge-base --is-ancestor HEAD "origin/$CURRENT_BRANCH" 2>/dev/null; then
    echo "  A new version is available on GitHub."
    echo

    # Show new commits
    echo "  New commits:"
    "$GIT_PATH" --no-pager log --oneline --graph --decorate "HEAD..origin/$CURRENT_BRANCH" 2>/dev/null
    echo

    read -rp "Do you want to update now? (Y/N): " UPDATE_CHOICE
    if [[ "$UPDATE_CHOICE" != "Y" && "$UPDATE_CHOICE" != "y" ]]; then
        echo
        echo "Update skipped."
        exit 0
    fi

    echo
    echo "Updating..."

    # Refresh index
    "$GIT_PATH" update-index --refresh &>/dev/null || true

    # Check for uncommitted changes
    if ! "$GIT_PATH" diff-index --quiet HEAD -- 2>/dev/null; then
        echo
        echo "[Info] Checking for potential conflicts..."

        # Get locally modified files
        LOCAL_CHANGES="$("$GIT_PATH" diff --name-only HEAD 2>/dev/null || echo "")"
        REMOTE_CHANGES="$("$GIT_PATH" diff --name-only "HEAD..origin/$CURRENT_BRANCH" 2>/dev/null || echo "")"

        # Check for conflicting files
        HAS_CONFLICTS=0
        BACKUP_DIR="$SCRIPT_DIR/.update_backup_$(date +%Y%m%d_%H%M%S)"

        while IFS= read -r local_file; do
            [[ -z "$local_file" ]] && continue
            if echo "$REMOTE_CHANGES" | grep -qxF "$local_file"; then
                HAS_CONFLICTS=1

                # Create backup directory if not exists
                if [[ ! -d "$BACKUP_DIR" ]]; then
                    mkdir -p "$BACKUP_DIR"
                    echo
                    echo "[Backup] Creating backup directory: $BACKUP_DIR"
                fi

                # Backup the file
                echo "[Backup] Backing up: $local_file"
                FILE_DIR="$(dirname "$local_file")"
                if [[ "$FILE_DIR" != "." ]]; then
                    mkdir -p "$BACKUP_DIR/$FILE_DIR"
                fi
                cp "$local_file" "$BACKUP_DIR/$local_file" 2>/dev/null || true
            fi
        done <<< "$LOCAL_CHANGES"

        if [[ $HAS_CONFLICTS -eq 1 ]]; then
            echo
            echo "========================================"
            echo "[Warning] Potential conflicts detected!"
            echo "========================================"
            echo
            echo "Your modified files may conflict with remote updates."
            echo "Your changes have been backed up to:"
            echo "  $BACKUP_DIR"
            echo

            read -rp "Continue with update? (Y/N): " CONFLICT_CHOICE
            if [[ "$CONFLICT_CHOICE" != "Y" && "$CONFLICT_CHOICE" != "y" ]]; then
                echo
                echo "Update cancelled. Your backup remains at: $BACKUP_DIR"
                exit 0
            fi
            echo
            echo "[Restore] Proceeding with update..."
        else
            echo
            echo "[Info] No conflicts detected. Safe to stash and update."
            echo

            read -rp "Stash your changes and continue? (Y/N): " STASH_CHOICE
            if [[ "$STASH_CHOICE" == "Y" || "$STASH_CHOICE" == "y" ]]; then
                echo "Stashing changes..."
                "$GIT_PATH" stash push -m "Auto-stash before update - $(date)"
            else
                echo
                echo "Update cancelled."
                exit 0
            fi
        fi
    fi

    # Check for untracked files that could be overwritten
    UNTRACKED_FILES="$("$GIT_PATH" ls-files --others --exclude-standard 2>/dev/null || echo "")"
    STASHED_UNTRACKED=0

    if [[ -n "$UNTRACKED_FILES" ]]; then
        # Check if any untracked files conflict with incoming changes
        REMOTE_ALL_FILES="$("$GIT_PATH" diff --name-only --diff-filter=A "HEAD..origin/$CURRENT_BRANCH" 2>/dev/null || echo "")"
        CONFLICTING_UNTRACKED=""

        while IFS= read -r ufile; do
            [[ -z "$ufile" ]] && continue
            if echo "$REMOTE_ALL_FILES" | grep -qxF "$ufile"; then
                CONFLICTING_UNTRACKED="${CONFLICTING_UNTRACKED}${ufile}"$'\n'
            fi
        done <<< "$UNTRACKED_FILES"

        if [[ -n "$CONFLICTING_UNTRACKED" ]]; then
            echo
            echo "========================================"
            echo "[Warning] Untracked files conflict with update!"
            echo "========================================"
            echo
            echo "The following untracked files would be overwritten:"
            echo "$CONFLICTING_UNTRACKED" | sed '/^$/d; s/^/  /'
            echo

            read -rp "Stash untracked files before updating? (Y/N): " STASH_UNTRACKED_CHOICE
            if [[ "$STASH_UNTRACKED_CHOICE" != "Y" && "$STASH_UNTRACKED_CHOICE" != "y" ]]; then
                echo
                echo "Update cancelled. Please move or remove the conflicting files manually."
                exit 1
            fi

            echo "Stashing all changes including untracked files..."
            if "$GIT_PATH" stash push --include-untracked -m "pre-update-$(date +%s)"; then
                STASHED_UNTRACKED=1
                echo "[Stash] Changes stashed successfully."
            else
                echo "[Error] Failed to stash changes. Update aborted."
                exit 1
            fi
            echo
        fi
    fi

    # Pull changes
    echo "Pulling latest changes..."
    if "$GIT_PATH" reset --hard "origin/$CURRENT_BRANCH" &>/dev/null; then
        echo
        echo "========================================"
        echo "Update completed successfully!"
        echo "========================================"
        echo

        if [[ -d "${BACKUP_DIR:-}" ]]; then
            echo "[Important] Your modified files were backed up to:"
            echo "  $BACKUP_DIR"
            echo
            echo "To restore your changes:"
            echo "  1. Run ./merge_config.sh to compare and merge files"
            echo "  2. Or manually compare backup with new version"
            echo
        fi

        if [[ $STASHED_UNTRACKED -eq 1 ]]; then
            echo "[Stash] Untracked files were stashed before the update."
            echo "  To restore them:  git stash pop"
            echo "  To discard them:  git stash drop"
            echo
            echo "  Note: 'git stash pop' may produce merge conflicts if"
            echo "  the update modified the same files. Resolve manually."
            echo
        fi

        echo "Please restart the application to use the new version."
        exit 0
    else
        echo
        echo "[Error] Update failed."
        if [[ $STASHED_UNTRACKED -eq 1 ]]; then
            echo "[Stash] Restoring stashed changes..."
            if "$GIT_PATH" stash pop &>/dev/null; then
                echo "[Stash] Changes restored successfully."
            else
                echo "[Stash] Could not auto-restore. Run 'git stash pop' manually."
            fi
        fi
        if [[ -d "${BACKUP_DIR:-}" ]]; then
            echo "Your backup is still available at: $BACKUP_DIR"
        fi
        exit 1
    fi
else
    echo "  [Warning] Local version has diverged from remote."
    echo "  This might be because you have local commits."
    echo "  Please update manually or consult the documentation."
    exit 0
fi
