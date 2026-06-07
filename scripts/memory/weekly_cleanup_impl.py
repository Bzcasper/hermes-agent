#!/usr/bin/env python3
"""Weekly cleanup implementation"""
import requests, json, time
from pathlib import Path
from collections import defaultdict

API_KEY = "m0-SRyuQMlpZ3BacFoGrb1Teg2fSr8isdmVCl4IlCkF"
HEADERS = {"Authorization": f"Token {API_KEY}", "Content-Type": "application/json"}

NOISE_PREFIXES = [
    "User started a claude-code session",
    "User executed a hermes:terminal command",
    "User executed a terminal command",
    "User executed a hermes terminal command",
    "User executed the hermes:terminal command",
    "User executed the terminal command",
]

def list_all():
    all_m = []
    page = 1
    while True:
        r = requests.get("https://api.mem0.ai/v1/memories/",
            headers=HEADERS,
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

def delete(mid):
    r = requests.delete(f"https://api.mem0.ai/v1/memories/{mid}/",
        headers=HEADERS, timeout=10)
    return r.status_code == 200

memories = list_all()
before_count = len(memories)
before_chars = sum(len(m.get("memory", "")) for m in memories)

# Delete noise
noise_ids = []
for m in memories:
    text = m.get("memory", "")
    for prefix in NOISE_PREFIXES:
        if text.startswith(prefix):
            noise_ids.append(m["id"])
            break

for mid in noise_ids:
    delete(mid)
    time.sleep(0.2)

# Dedup
memories = list_all()
prefix_groups = defaultdict(list)
for m in memories:
    prefix_groups[m.get("memory", "")[:50]].append(m)

dedup_ids = []
for group in prefix_groups.values():
    if len(group) > 1:
        for m in group[1:]:
            dedup_ids.append(m["id"])

for mid in dedup_ids:
    delete(mid)
    time.sleep(0.2)

# Final stats
memories = list_all()
after_count = len(memories)
after_chars = sum(len(m.get("memory", "")) for m in memories)

print(json.dumps({
    "before_count": before_count,
    "after_count": after_count,
    "before_chars": before_chars,
    "after_chars": after_chars,
    "noise_deleted": len(noise_ids),
    "dedup_deleted": len(dedup_ids),
}))
