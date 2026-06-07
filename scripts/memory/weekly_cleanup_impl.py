#!/usr/bin/env python3
"""Weekly cleanup: noise removal, near-dedup, sacred protection."""
import sys, json, time, requests
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, "/root/.hermes/scripts")
from mem0_wrapper_v1 import _load_api_key, _log_event

NOISE_PREFIXES = [
    "User started a claude-code session",
    "User executed a hermes:terminal command",
    "User executed a terminal command",
    "User executed a hermes terminal command",
    "User executed the hermes:terminal command",
    "User executed the terminal command",
]

def list_all():
    api_key = _load_api_key()
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
    all_m = []
    page = 1
    while True:
        r = requests.get("https://api.mem0.ai/v1/memories/",
            headers=headers,
            params={"user_id": "boss", "page_size": 100, "page": page},
            timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        items = data if isinstance(data, list) else data.get("results", [])
        all_m.extend(items)
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.3)
    return all_m

def delete(mid, api_key):
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
    r = requests.delete(f"https://api.mem0.ai/v1/memories/{mid}/",
        headers=headers, timeout=10)
    return r.status_code == 200

def run_cleanup(dry_run=True):
    api_key = _load_api_key()
    memories = list_all()
    before_count = len(memories)
    before_chars = sum(len(m.get("memory", "")) for m in memories)

    # Delete noise (skip sacred)
    noise_ids = []
    for m in memories:
        if (m.get("metadata") or {}).get("sacred"):
            continue
        text = m.get("memory", "")
        for prefix in NOISE_PREFIXES:
            if text.startswith(prefix):
                noise_ids.append(m["id"])
                break

    if not dry_run:
        for mid in noise_ids:
            delete(mid, api_key)
            time.sleep(0.2)

    # Dedup (skip sacred)
    memories = list_all()
    prefix_groups = defaultdict(list)
    for m in memories:
        if (m.get("metadata") or {}).get("sacred"):
            continue
        prefix_groups[m.get("memory", "")[:50]].append(m)

    dedup_ids = []
    for group in prefix_groups.values():
        if len(group) > 1:
            for m in group[1:]:
                dedup_ids.append(m["id"])

    if not dry_run:
        for mid in dedup_ids:
            delete(mid, api_key)
            time.sleep(0.2)

    # Final stats
    memories = list_all()
    after_count = len(memories)
    after_chars = sum(len(m.get("memory", "")) for m in memories)

    result = {
        "before_count": before_count,
        "after_count": after_count,
        "before_chars": before_chars,
        "after_chars": after_chars,
        "noise_deleted": len(noise_ids),
        "dedup_deleted": len(dedup_ids),
    }
    
    _log_event({"action": "weekly_cleanup", **result, "dry_run": dry_run})
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    
    result = run_cleanup(dry_run=not args.apply)
    print(json.dumps(result, indent=2))
