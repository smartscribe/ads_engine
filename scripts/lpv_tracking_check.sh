#!/usr/bin/env bash
# Monthly regression check for Meta Pixel tracking on jotpsych.com.
# Verifies the CSP still whitelists Facebook and the site still fires the
# canonical WebApp Actions pixel. Fails loud if either regresses.
#
# Background: on 2026-04-14 the site's CSP was missing Facebook hosts,
# which silently blocked fbevents.js and dropped Meta's LPV/link-click
# ratio to 6% (industry norm 70-90%). See
# plans/lpv-tracking-fix-2026-04-14.md for the full incident writeup.

set -euo pipefail

SITE="${1:-https://jotpsych.com}"
EXPECTED_PIXEL="1625233994894344"

pass=0
fail=0

check() {
    local label="$1"
    local ok="$2"
    if [[ "$ok" == "1" ]]; then
        echo "  PASS  $label"
        pass=$((pass + 1))
    else
        echo "  FAIL  $label"
        fail=$((fail + 1))
    fi
}

echo "LPV tracking check — $SITE"
echo

csp=$(curl -sIL "$SITE/" | awk 'tolower($1) == "content-security-policy:" { $1=""; print }')
[[ "$csp" == *"https://connect.facebook.net"* ]] && fb_script=1 || fb_script=0
[[ "$csp" == *"https://www.facebook.com"* ]] && fb_connect=1 || fb_connect=0
check "CSP script-src allows connect.facebook.net" "$fb_script"
check "CSP connect-src allows www.facebook.com" "$fb_connect"

for path in "" "features" "audit" "pricing" "for-clinics"; do
    html=$(curl -sL "$SITE/$path")
    if [[ "$html" == *"fbq('init','$EXPECTED_PIXEL')"* ]]; then
        check "/$path fires pixel $EXPECTED_PIXEL" "1"
    else
        check "/$path fires pixel $EXPECTED_PIXEL" "0"
    fi
done

echo
echo "passed: $pass  failed: $fail"
[[ "$fail" == "0" ]] || exit 1

echo
echo "Next: after a deploy or monthly, re-pull Meta Ads insights for the last"
echo "7 days and confirm LPV/link-click ratio is above 50% (target 70%+)."
echo "If not, CSP passed but something else is dropping the pixel signal."
