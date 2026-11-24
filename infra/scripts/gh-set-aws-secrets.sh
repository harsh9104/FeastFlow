#!/usr/bin/env bash
# Copy the current Learner Lab keys from ~/.aws/credentials ([default]) into the GitHub repo's
# Actions secrets, so the CI/CD deploy job can reach AWS. Run after every Start Lab (keys expire).
# Needs the GitHub CLI, logged in (gh auth login), run from inside this repo.
# Without gh: GitHub → repo → Settings → Secrets and variables → Actions → set the same 3 secrets.
set -euo pipefail
command -v gh >/dev/null || { echo "gh (GitHub CLI) not found: install it, or set the secrets in the GitHub web UI"; exit 1; }
CREDS="${AWS_SHARED_CREDENTIALS_FILE:-$HOME/.aws/credentials}"
[ -f "$CREDS" ] || { echo "$CREDS not found: paste the lab's AWS CLI block there first"; exit 1; }

value() {  # value KEY -> the KEY from the [default] section
  awk -v k="$1" '
    /^\[/ { in_default = ($0 ~ /^\[default\]/) }
    in_default && $0 ~ "^[ \t]*" k "[ \t]*=" { sub(/^[^=]*=[ \t]*/, ""); sub(/[ \t\r]+$/, ""); print; exit }
  ' "$CREDS"
}

for key in aws_access_key_id aws_secret_access_key aws_session_token; do
  v="$(value "$key")"
  [ -n "$v" ] || { echo "$key missing from [default] in $CREDS"; exit 1; }
  printf '%s' "$v" | gh secret set "$(tr '[:lower:]' '[:upper:]' <<<"$key")"
done
echo "GitHub secrets updated. Re-run a failed deploy from the Actions tab, or push to main."
