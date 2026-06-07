#!/usr/bin/env python3
"""P2.2: Expiration policy for ephemeral memories."""
import json, time, sys
from datetime import datetime, timezone, timedelta
from mem0_wrapper_v1 import list_l3, delete_l3, _log_event

def cleanup_expired(dry_run=True):
    """Remove memories past their expiration_date."""
    memories = list_l3()
    now = datetime.now(timezone.utc)
    expired = []
    
    for m in memories:
        exp = m.get("expiration_date")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if exp_dt < now:
                    expired.append(m)
            except (ValueError, TypeError):
                continue
    
    print(f"Found {len(expired)} expired memories")
    
    deleted = 0
    for m in expired:
        if dry_run:
            print(f"  WOULD DELETE: {m['id'][:12]}... expires={m.get('expiration_date')}")
        else:
            if delete_l3(m["id"]):
                _log_event({"action": "expiration_cleanup", "id": m["id"]})
                deleted += 1
            time.sleep(0.2)
    
    return deleted if not dry_run else len(expired)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    
    deleted = cleanup_expired(dry_run=not args.apply)
    if args.apply:
        print(f"Deleted {deleted} expired memories")
    else:
        print("DRY RUN. Use --apply to execute.")
