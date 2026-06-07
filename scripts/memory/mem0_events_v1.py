#!/usr/bin/env python3
"""P3.1: Events poller for L3 memory changes."""
import json, time
from pathlib import Path
from datetime import datetime, timezone
from mem0_wrapper_v1 import _get_session, MEM0_API_BASE, _log_event

LOG_FILE = Path.home() / ".hermes" / "logs" / "mem0_events.jsonl"

def poll_events():
    """Poll recent events from mem0."""
    session = _get_session()
    
    try:
        resp = session.get(f"{MEM0_API_BASE}/events/", timeout=15)
        if resp.status_code == 200:
            events = resp.json()
            with open(LOG_FILE, "a") as f:
                for e in events if isinstance(events, list) else []:
                    f.write(json.dumps(e) + "\n")
            return events
    except Exception as e:
        _log_event({"action": "events_poll_error", "error": str(e)})
    
    return []

if __name__ == "__main__":
    events = poll_events()
    print(f"Events: {len(events) if isinstance(events, list) else 0}")
