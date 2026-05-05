#!/usr/bin/env python3
"""
Sync Stripe customers to Meta Custom Audience exclusion list.
Pulls all customers with completed trials/subscriptions from Stripe,
hashes their emails (SHA256), and uploads to Meta as a Custom Audience.

Run daily via cron:
  0 6 * * * python3 scripts/sync-stripe-exclusions.py

Requirements: pip install stripe
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# =====================================================================
# CONFIG
# =====================================================================
STRIPE_KEY = os.environ["STRIPE_SECRET_KEY"]
META_TOKEN = os.environ["META_ADS_ACCESS_TOKEN"]
META_ACCOUNT = "act_1582817295627677"
AUDIENCE_NAME = "Stripe Customers - Auto Exclusion"
META_API_VERSION = "v21.0"
LOG_DIR = "/Users/nathanpeereboom/ads_engine/data/exclusion-logs"

# =====================================================================
# STRIPE: Pull all customer emails
# =====================================================================
def fetch_stripe_customers():
    """Pull all customers from Stripe who have had any subscription or payment."""
    try:
        import stripe
    except ImportError:
        print("Installing stripe package...")
        subprocess.run([sys.executable, "-m", "pip", "install", "stripe", "-q"])
        import stripe
    
    stripe.api_key = STRIPE_KEY
    
    emails = set()
    has_more = True
    starting_after = None
    
    print("Fetching Stripe customers...")
    while has_more:
        params = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after
        
        customers = stripe.Customer.list(**params)
        
        for customer in customers.data:
            if customer.email:
                emails.add(customer.email.lower().strip())
            starting_after = customer.id
        
        has_more = customers.has_more
        print(f"  ...{len(emails)} unique emails so far")
    
    return emails


# =====================================================================
# META: Upload hashed emails as Custom Audience
# =====================================================================
def meta_api_post(endpoint, data):
    url = f"https://graph.facebook.com/{META_API_VERSION}/{endpoint}"
    data["access_token"] = META_TOKEN
    cmd = ["curl", "-s", "-X", "POST", url]
    for k, v in data.items():
        cmd.extend(["-F", f"{k}={v}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


def meta_api_get(path):
    url = f"https://graph.facebook.com/{META_API_VERSION}/{path}?access_token={META_TOKEN}"
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
    return json.loads(result.stdout)


def find_or_create_audience():
    """Find existing auto-exclusion audience or create a new one."""
    # Search for existing
    resp = meta_api_get(f"{META_ACCOUNT}/customaudiences?fields=id,name&limit=100")
    for aud in resp.get("data", []):
        if aud["name"] == AUDIENCE_NAME:
            print(f"  Found existing audience: {aud['id']}")
            return aud["id"]
    
    # Create new
    resp = meta_api_post(f"{META_ACCOUNT}/customaudiences", {
        "name": AUDIENCE_NAME,
        "subtype": "CUSTOM",
        "description": "Auto-synced from Stripe. All customers with accounts. Used as exclusion list.",
        "customer_file_source": "USER_PROVIDED_ONLY",
    })
    if "error" in resp:
        print(f"  Error creating audience: {resp['error'].get('message','')}")
        sys.exit(1)
    
    print(f"  Created new audience: {resp['id']}")
    return resp["id"]


def upload_to_audience(audience_id, emails):
    """Hash emails and upload to Meta Custom Audience (replace mode)."""
    # SHA256 hash each email (Meta's requirement)
    hashed = [hashlib.sha256(e.encode()).hexdigest() for e in emails]
    
    # Upload in batches of 10,000
    total_uploaded = 0
    batch_size = 10000
    
    for i in range(0, len(hashed), batch_size):
        batch = hashed[i:i+batch_size]
        
        payload = {
            "schema": "EMAIL_SHA256",
            "data": json.dumps(batch),
        }
        
        # First batch replaces, subsequent batches append
        if i == 0:
            # Clear and replace: use the sessions API
            # Start a replace session
            session = meta_api_post(f"{audience_id}/usersreplace", {
                "payload": json.dumps({
                    "schema": ["EMAIL_SHA256"],
                    "data": [[h] for h in batch]
                }),
                "session": json.dumps({
                    "session_id": int(time.time()),
                    "estimated_num_total": len(hashed),
                    "batch_seq": 1,
                    "last_batch_flag": len(hashed) <= batch_size,
                })
            })
            if "error" in session:
                # Fallback: use regular users endpoint
                print(f"  Replace session failed, using append: {session['error'].get('message','')[:60]}")
                resp = meta_api_post(f"{audience_id}/users", {
                    "payload": json.dumps({
                        "schema": ["EMAIL_SHA256"],
                        "data": [[h] for h in batch]
                    })
                })
                if "error" in resp:
                    print(f"  Upload error: {resp['error'].get('message','')}")
                    return 0
                total_uploaded += int(resp.get("num_received", 0))
            else:
                total_uploaded += int(session.get("num_received", len(batch)))
        else:
            resp = meta_api_post(f"{audience_id}/users", {
                "payload": json.dumps({
                    "schema": ["EMAIL_SHA256"],
                    "data": [[h] for h in batch]
                })
            })
            if "error" not in resp:
                total_uploaded += int(resp.get("num_received", 0))
        
        print(f"  Batch {i//batch_size + 1}: uploaded {total_uploaded} so far")
        time.sleep(1)
    
    return total_uploaded


# =====================================================================
# MAIN
# =====================================================================
def main():
    start = datetime.now()
    print(f"=== Stripe -> Meta Exclusion Sync: {start.isoformat()} ===\n")
    
    # 1. Pull Stripe customers
    emails = fetch_stripe_customers()
    print(f"\nTotal unique emails from Stripe: {len(emails)}")
    
    if not emails:
        print("No emails found. Exiting.")
        return
    
    # 2. Find or create Meta audience
    print("\nMeta Custom Audience:")
    audience_id = find_or_create_audience()
    
    # 3. Upload
    print(f"\nUploading {len(emails)} hashed emails...")
    uploaded = upload_to_audience(audience_id, emails)
    
    # 4. Log
    os.makedirs(LOG_DIR, exist_ok=True)
    log_entry = {
        "timestamp": start.isoformat(),
        "stripe_customers": len(emails),
        "meta_audience_id": audience_id,
        "uploaded": uploaded,
        "duration_seconds": (datetime.now() - start).total_seconds(),
    }
    log_file = os.path.join(LOG_DIR, f"sync-{start.strftime('%Y-%m-%d')}.json")
    with open(log_file, "w") as f:
        json.dump(log_entry, f, indent=2)
    
    print(f"\nDone. {uploaded} records sent to audience {audience_id}")
    print(f"Log: {log_file}")
    print(f"Duration: {log_entry['duration_seconds']:.1f}s")


if __name__ == "__main__":
    main()

