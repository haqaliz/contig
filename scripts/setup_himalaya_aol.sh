#!/bin/bash
# Configure himalaya for AOL Mail. Prompts for the address and password; the
# password goes into macOS Keychain, never into the config or shell history.
#
# AOL: IMAP imap.aol.com:993 TLS; SMTP smtp.aol.com:465 TLS; full AOL address;
# app password if 2-Step Verification is on (AOL Account Security).
set -euo pipefail

if ! command -v himalaya >/dev/null 2>&1; then
  echo "himalaya is not installed. Run: brew install himalaya" >&2
  exit 1
fi

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/himalaya"
CONFIG="$CONFIG_DIR/config.toml"
if [ -f "$CONFIG" ]; then
  echo "Existing himalaya config found at $CONFIG." >&2
  echo "Back it up or merge the aol account manually; this script will not overwrite it." >&2
  exit 1
fi

read -rp "AOL email address: " AOL_ADDRESS
if [[ "$AOL_ADDRESS" != *"@aol.com" ]]; then
  echo "warning: '$AOL_ADDRESS' does not end in @aol.com" >&2
fi
read -rsp "AOL password (use an app password if 2-Step Verification is on): " AOL_PASS; echo

security add-generic-password -U -a aol-smtp -s himalaya -w "$AOL_PASS"
unset AOL_PASS

mkdir -p "$CONFIG_DIR"
cat > "$CONFIG" <<EOF
[accounts.aol]
email = "$AOL_ADDRESS"
display-name = "Ali Haqiqi"

imap.server = "imaps://imap.aol.com:993"
imap.sasl.plain.username = "$AOL_ADDRESS"
imap.sasl.plain.password.command = "security find-generic-password -a aol-smtp -s himalaya -w"

smtp.server = "smtps://smtp.aol.com:465"
smtp.sasl.plain.username = "$AOL_ADDRESS"
smtp.sasl.plain.password.command = "security find-generic-password -a aol-smtp -s himalaya -w"
EOF
chmod 600 "$CONFIG"

echo "Wrote $CONFIG (password in Keychain: aol-smtp/himalaya)."
echo "Testing IMAP + SMTP login (no message is sent)..."
himalaya account check -a aol

cat <<EOF

Next:
  1. Regenerate previews with the real From address:
     CONTIG_SMTP_FROM="$AOL_ADDRESS" python scripts/send_outreach.py \\
       --messages docs/validation/outreach_messages_batch1.json \\
       --out-dir /tmp/outreach-eml-aol

  2. Send one message:
     himalaya message send -a aol /tmp/outreach-eml-aol/central-south-glh.eml

  3. Send the rest:
     himalaya message send -a aol /tmp/outreach-eml-aol/amp.eml
     himalaya message send -a aol /tmp/outreach-eml-aol/panelapp.eml

If AOL rejects the login, confirm 2-Step Verification + app password in AOL
Account Security. The From header must match the authenticated AOL account.
EOF
