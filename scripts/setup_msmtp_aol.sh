#!/bin/bash
# Configure msmtp for AOL Mail. Prompts for the address and app password;
# the password goes into macOS Keychain, never into the config or shell history.
#
# AOL requirements: SMTP smtp.aol.com, port 465 SSL, full AOL address, and an
# app password if 2-Step Verification is on (AOL Account Security -> Generate
# app password). If your account has no app-password option, use Gmail instead.
set -euo pipefail

if ! command -v msmtp >/dev/null 2>&1; then
  echo "msmtp is not installed. Run: brew install msmtp" >&2
  exit 1
fi

read -rp "AOL email address: " AOL_ADDRESS
if [[ "$AOL_ADDRESS" != *"@aol.com" ]]; then
  echo "warning: '$AOL_ADDRESS' does not end in @aol.com" >&2
fi
read -rsp "AOL password (use an app password if 2-Step Verification is on): " AOL_PASS; echo

security add-generic-password -U -a aol-smtp -s msmtp -w "$AOL_PASS"
unset AOL_PASS

CONFIG="$HOME/.msmtprc"
CA_BUNDLE="/opt/homebrew/etc/ca-certificates/cert.pem"
[ -f "$CA_BUNDLE" ] || CA_BUNDLE="/etc/ssl/cert.pem"
cat > "$CONFIG" <<EOF
defaults
auth on
tls on
tls_starttls off
tls_trust_file $CA_BUNDLE
logfile ~/.msmtp.log
timeout 30

account aol
host smtp.aol.com
port 465
user $AOL_ADDRESS
from $AOL_ADDRESS
passwordeval security find-generic-password -a aol-smtp -s msmtp -w

account default : aol
EOF
chmod 600 "$CONFIG"

echo "Wrote $CONFIG (password in Keychain: aol-smtp/msmtp)."
echo "Testing the AOL SMTP login (no message is sent)..."
msmtp --serverinfo -a aol

cat <<EOF

Next:
  1. Regenerate previews with the real From address:
     CONTIG_SMTP_FROM="$AOL_ADDRESS" python scripts/send_outreach.py \\
       --messages docs/validation/outreach_messages_batch1.json \\
       --out-dir /tmp/outreach-eml-aol

  2. Send one message:
     msmtp -a aol -t < /tmp/outreach-eml-aol/central-south-glh.eml

  3. Send the rest:
     msmtp -a aol -t < /tmp/outreach-eml-aol/amp.eml
     msmtp -a aol -t < /tmp/outreach-eml-aol/panelapp.eml

The From address must match the authenticated AOL account. If AOL rejects the
login, confirm 2-Step Verification + app password in AOL Account Security.
EOF
