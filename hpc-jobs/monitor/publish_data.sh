#!/bin/bash
# Push site/data (status.json and the per cell detail files) to the
# monitor-data branch as one fresh commit, replacing the previous one, so
# the branch never grows. Works in its own scratch folder, so the working
# tree and its branch are never touched. Uses only the deploy key.
set -euo pipefail

MONITOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="${MONITOR_REPO_URL:-git@github.com:ClimateImpactLab/socioeconomics.git}"
BRANCH="monitor-data"
DEPLOY_KEY="${MONITOR_DEPLOY_KEY:-$HOME/.ssh/cil_monitor_deploy}"
PUBLISH_DIR="$MONITOR_DIR/.publish"

if [ ! -f "$MONITOR_DIR/site/data/status.json" ]; then
    echo "no site/data/status.json to publish" >&2
    exit 1
fi
if [ ! -f "$DEPLOY_KEY" ]; then
    echo "deploy key not found: $DEPLOY_KEY (see README, Automatic updates)" >&2
    exit 1
fi

rm -rf "$PUBLISH_DIR"
mkdir -p "$PUBLISH_DIR"
cp -R "$MONITOR_DIR/site/data" "$PUBLISH_DIR/data"

cd "$PUBLISH_DIR"
git init -q
git checkout -q -b "$BRANCH"
git add data
git -c user.name="amel-monitor" -c user.email="amel-monitor@users.noreply.github.com" \
    commit -q -m "Monitor data, $(date -u '+%Y-%m-%d %H:%M UTC')"

GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o BatchMode=yes" \
    git push -q -f "$REPO_URL" "$BRANCH:$BRANCH"

echo "published $(du -sh data | cut -f1) to $BRANCH"
cd "$MONITOR_DIR"
rm -rf "$PUBLISH_DIR"
