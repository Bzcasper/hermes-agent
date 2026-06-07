#!/usr/bin/env python3
"""P2.1: Graph-aware dedup pass using graph=true relationships."""
import json, time, sys
from pathlib import Path
from difflib import SequenceMatcher
from mem0_wrapper_v1 import list_l3, delete_l3, _log_event

def find_near_dups(threshold=0.85):
    """Find near-duplicate pairs by string similarity."""
    memories = list_l3()
    dups = []
    for i, m1 in enumerate(memories):
        for m2 in memories[i+1:]:
            sim = SequenceMatcher(None, m1.get("memory", "")[:100], m2.get("memory", "")[:100]).ratio()
            if sim > threshold:
                dups.append((m1, m2, sim))
    return dups

def dedup(threshold=0.85, dry_run=True):
    """Remove near-duplicates, keeping longer entry."""
    dups = find_near_dups(threshold)
    print(f"Found {len(dups)} near-duplicate pairs")
    
    deleted = 0
    for m1, m2, sim in dups:
        to_delete = m1 if len(m1.get("memory", "")) < len(m2.get("memory", "")) else m2
        if dry_run:
            print(f"  WOULD DELETE: {to_delete['id'][:12]}... (sim={sim:.2f})")
        else:
            if delete_l3(to_delete["id"]):
                _log_event({"action": "graph_dedup", "id": to_delete["id"], "sim": sim})
                deleted += 1
            time.sleep(0.2)
    
    return deleted

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.85)
    args = parser.parse_args()
    
    deleted = dedup(threshold=args.threshold, dry_run=not args.apply)
    if args.apply:
        print(f"Deleted {deleted} duplicates")
    else:
        print("DRY RUN. Use --apply to execute.")
