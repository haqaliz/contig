#!/bin/bash
# Update the AOL password used by the existing himalaya config. This does not
# touch ~/.config/himalaya/config.toml; it only replaces the Keychain item.
#
# AOL third-party apps require an app password, not the normal account
# password. Generate one at https://login.aol.com/myaccount/security
# ("Generate app password"). Use a browser you have used for AOL for several
# days, not Incognito. If AOL reported too many bad auth attempts, wait 15-30
# minutes before testing again.
set -euo pipefail

if [ ! -f "${XDG_CONFIG_HOME:-$HOME/.config}/himalaya/config.toml" ]; then
  echo "No himalaya config found. Run scripts/setup_himalaya_aol.sh first." >&2
  exit 1
fi

read -rsp "New AOL app password: " AOL_PASS; echo
security add-generic-password -U -a aol-smtp -s himalaya -w "$AOL_PASS"
unset AOL_PASS

echo "Updated Keychain item aol-smtp/himalaya."
echo "If AOL just reported too many bad auth attempts, wait 15-30 minutes."
echo "Then test once with: himalaya account check -a aol"
