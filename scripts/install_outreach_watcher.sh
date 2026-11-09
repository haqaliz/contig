#!/bin/bash
# Install a 15-minute macOS LaunchAgent that runs the deterministic outreach
# reply watcher. It only writes a local digest; it never replies.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/com.contig.outreach-replies.plist"
LABEL="com.contig.outreach-replies"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/scripts/check_outreach_replies.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartInterval</key>
  <integer>900</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/contig-outreach.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/contig-outreach.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "Installed $LABEL (every 15 minutes)."
echo "Log: $HOME/Library/Logs/contig-outreach.log"
echo "Digest: ~/.local/state/contig-outreach/replies.md"
echo "Uninstall: launchctl bootout gui/$(id -u) '$PLIST' && rm '$PLIST'"
