#!/usr/bin/env python3
"""P2.2: Expiration policy for ephemeral memories."""
import json, time, sys
from datetime import datetime, timezone, timedelta
from mem0_wrapper_v1 import list_l3, delete_l3, _log_event

def cleanup_expired():
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
    for m in expired:
        print(f"  {m['id'][:12]}... expires={m.get('expiration_date')}")
    
    return expired

if __name__ == "__main__":
    expired = cleanup_expired()
    print(f"Expired: {len(expired)}")
