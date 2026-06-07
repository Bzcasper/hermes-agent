#!/usr/bin/env python3
"""P2.3: Export pipeline for L3 memory backup."""
import json, time
from pathlib import Path
from datetime import datetime, timezone
from mem0_wrapper_v1 import list_l3, _log_event, _get_session, MEM0_API_BASE

EXPORT_DIR = Path.home() / ".hermes" / "backups"

def export_memories():
    """Export all memories to local JSONL."""
    EXPORT_DIR.mkdir(exist_ok=True)
    
    memories = list_l3()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    export_file = EXPORT_DIR / f"mem0_export_{ts}.jsonl"
    
    with open(export_file, "w") as f:
        for m in memories:
            f.write(json.dumps(m) + "\n")
    
    _log_event({"action": "export", "count": len(memories), "file": str(export_file)})
    print(f"Exported {len(memories)} memories to {export_file}")
    return export_file

if __name__ == "__main__":
    export_memories()
