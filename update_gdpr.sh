#!/usr/bin/env bash
# GDPRScanner — self-update script.
#
# Pulls the latest release from origin, reinstalls dependencies if they
# changed, and restarts the systemd service if one is installed.
# Safe to run from cron: exits quietly when already up to date, and
# auto-stashes local hotfixes instead of aborting the merge.
#
# Usage:
#   ./update_gdpr.sh             # update if origin has new commits
#   ./update_gdpr.sh --check     # report status only, change nothing
#
# Environment:
#   GDPR_BRANCH    branch to track            (default: main)
#   GDPR_SERVICE   systemd unit to restart    (default: gdprscanner, if it exists)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH="${GDPR_BRANCH:-main}"
SERVICE="${GDPR_SERVICE:-gdprscanner}"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

cd "$SCRIPT_DIR"

if [ ! -d .git ]; then
    log "ERROR: $SCRIPT_DIR is not a git checkout — cannot self-update."
    exit 1
fi

git fetch origin "$BRANCH" --quiet

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
    log "Already up to date ($(git describe --always HEAD))."
    exit 0
fi

log "Update available: $(git rev-parse --short HEAD) -> $(git rev-parse --short "$REMOTE")"
git log --oneline "HEAD..origin/$BRANCH" | sed 's/^/    /'

if [ "${1:-}" = "--check" ]; then
    exit 0
fi

# Local edits (e.g. a hotfix applied directly on the server) would make the
# merge abort. Stash them so the update proceeds; the stash is kept so
# nothing is lost.
if ! git diff-index --quiet HEAD --; then
    log "Local changes detected — stashing:"
    git diff --stat HEAD | sed 's/^/    /'
    git stash push --quiet -m "update_gdpr.sh auto-stash $(date '+%Y-%m-%d %H:%M:%S')"
    log "Recover later with: git stash show -p / git stash pop"
fi

REQS_CHANGED=false
if ! git diff --quiet "HEAD..origin/$BRANCH" -- requirements.txt; then
    REQS_CHANGED=true
fi

# Fast-forward only: the server checkout must never diverge from origin.
git merge --ff-only --quiet "origin/$BRANCH"
log "Updated to $(git rev-parse --short HEAD)."

if [ "$REQS_CHANGED" = true ]; then
    log "requirements.txt changed — updating dependencies..."
    "$SCRIPT_DIR/venv/bin/pip" install --quiet -r requirements.txt
    log "Dependencies updated."
fi

if command -v systemctl >/dev/null 2>&1 \
        && systemctl list-unit-files --type=service 2>/dev/null | grep -q "^$SERVICE\.service"; then
    log "Restarting $SERVICE.service..."
    systemctl restart "$SERVICE"
    log "Service restarted."
else
    log "No systemd unit '$SERVICE' found — restart GDPRScanner manually."
fi

log "Done."
