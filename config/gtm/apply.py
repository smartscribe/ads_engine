#!/usr/bin/env python3
"""Apply Phase 1 GTM: rename tag 67 to ASCII hyphen, create tags 2 and 3."""
import json, subprocess, sys

DEST = "/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/ads_engine/config/gtm"
ACCT, CTNR, WS = "6258528322", "200880687", "24"
GTM = "/Users/nathanpeereboom/.claude/integrations/gtm_client.py"
TRIGGER_FIRSTNOTE, TRIGGER_SIGNUP, TRIGGER_CAL = "15", "65", "66"

def call(method, path, body=None):
    args = ["python3", GTM, "raw", method, path]
    if body is not None:
        args += ["--json", json.dumps(body)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAIL {method} {path}\n{r.stderr}"); sys.exit(1)
    return json.loads(r.stdout) if r.stdout.strip() else {}

def html_snippet(value, content_name, with_event_id):
    if with_event_id:
        return ('<script>(function(){var e="{{dlv_event_id}}";var p={value:' + str(value) +
                ',currency:"USD",content_name:"' + content_name +
                '"};if(e&&e!=="undefined"&&e!==""){fbq("track","Purchase",p,{eventID:e});}else{fbq("track","Purchase",p);}})();</script>')
    return ('<script>(function(){var p={value:' + str(value) +
            ',currency:"USD",content_name:"' + content_name + '"};fbq("track","Purchase",p);})();</script>')

def make_tag(name, html, trigger_ids):
    return {
        "name": name, "type": "html",
        "parameter": [
            {"type": "template", "key": "html", "value": html},
            {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}],
        "firingTriggerId": trigger_ids,
        "tagFiringOption": "oncePerEvent",
    }

# Use regular ASCII hyphen-space, matches existing container convention ("Meta - First Note Event")
NAME_FN = "Meta Purchase - First Note"
NAME_SU = "Meta Purchase - Sign Up"
NAME_CAL = "Meta Purchase - Calendar Scheduled"

# 1. Rename tag 67 from em-dash version to ASCII-hyphen version
print("=== Renaming tag 67 (em-dash) -> ASCII hyphen ===")
existing = call("GET", f"/accounts/{ACCT}/containers/{CTNR}/workspaces/{WS}/tags/67")
existing["name"] = NAME_FN
patched = call("PUT", f"/accounts/{ACCT}/containers/{CTNR}/workspaces/{WS}/tags/67", existing)
print(f"  tagId={patched.get('tagId')} name={patched.get('name')}")
with open(f"{DEST}/tags/meta-purchase-first-note.json", "w") as f:
    json.dump(make_tag(NAME_FN, html_snippet(150, "first_note", True), [TRIGGER_FIRSTNOTE]), f, indent=2)
with open(f"{DEST}/tags/meta-purchase-first-note.created.json", "w") as f:
    json.dump(patched, f, indent=2)

# 2. Sign Up tag
print("=== Creating Sign Up tag ===")
spec_su = make_tag(NAME_SU, html_snippet(25, "signup", True), [TRIGGER_SIGNUP])
c_su = call("POST", f"/accounts/{ACCT}/containers/{CTNR}/workspaces/{WS}/tags", spec_su)
print(f"  tagId={c_su.get('tagId')} name={c_su.get('name')}")
with open(f"{DEST}/tags/meta-purchase-sign-up.json", "w") as f:
    json.dump(spec_su, f, indent=2)
with open(f"{DEST}/tags/meta-purchase-sign-up.created.json", "w") as f:
    json.dump(c_su, f, indent=2)

# 3. Calendar tag
print("=== Creating Calendar Scheduled tag ===")
spec_cal = make_tag(NAME_CAL, html_snippet(5, "calendar", False), [TRIGGER_CAL])
c_cal = call("POST", f"/accounts/{ACCT}/containers/{CTNR}/workspaces/{WS}/tags", spec_cal)
print(f"  tagId={c_cal.get('tagId')} name={c_cal.get('name')}")
with open(f"{DEST}/tags/meta-purchase-calendar-scheduled.json", "w") as f:
    json.dump(spec_cal, f, indent=2)
with open(f"{DEST}/tags/meta-purchase-calendar-scheduled.created.json", "w") as f:
    json.dump(c_cal, f, indent=2)

print("\n=== Final state in workspace 24 ===")
all_tags = call("GET", f"/accounts/{ACCT}/containers/{CTNR}/workspaces/{WS}/tags")
for t in all_tags.get("tag", []):
    if "Meta Purchase" in t.get("name", ""):
        print(f"  tagId={t.get('tagId')} | {t.get('name'):45} | triggers={t.get('firingTriggerId')}")
