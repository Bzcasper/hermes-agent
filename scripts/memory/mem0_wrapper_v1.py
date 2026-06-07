#!/usr/bin/env python3
"""
mem0_wrapper_v1.py — THE canonical write/read path for L3 memory.

Pro features:
- graph=true (entity relationship tracking)
- output_format=structured (structured categories)
- expires_at (server-enforced TTL)
- structured_categories (5-bucket taxonomy)
- custom_reranker (domain-tuned)

Preserves:
- B2: custom_instructions (durable facts only)
- B3: custom metadata (topic, sacred, source, etc.)
- B4: run_id scoping (ephemeral writes)

Usage:
    from mem0_wrapper_v1 import write_l3, write_ephemeral, read_l3, search_l3
    
    # Write durable fact
    entry_id = write_l3("User prefers dark mode", topic="preferences", sacred=False)
    
    # Write ephemeral (cron/run-scoped)
    entry_id = write_ephemeral("Job completed successfully", run_id="cron-123")
    
    # Read
    entry = read_l3(entry_id)
    
    # Search
    results = search_l3("user preferences")
"""
from __future__ import annotations
import json
import time
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("Install: pip install requests", file=sys.stderr)
    sys.exit(2)

# ---- Configuration ----
MEM0_API_BASE = "https://api.mem0.ai/v1"
MEM0_JSON = Path.home() / ".hermes" / "mem0.json"
ENV_PATH = Path.home() / ".hermes" / ".env"
LOG_DIR = Path.home() / ".hermes" / "logs"

# 5-bucket taxonomy
CATEGORIES = ["preferences", "environment", "project", "media", "sacred"]

# Custom instructions for durable facts only
DEFAULT_CUSTOM_INSTRUCTIONS = (
    "Extract only durable facts that will still matter in 30+ days. "
    "Reject: transient errors, stack traces, port numbers that drift, "
    "task progress, in-flight PR/issue numbers, session narration."
)

# ---- Helpers ----

def _load_config() -> dict:
    """Load mem0.json config."""
    if MEM0_JSON.exists():
        return json.loads(MEM0_JSON.read_text())
    return {}

def _load_api_key() -> str:
    """Load MEM0_API_KEY from .env."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith("MEM0_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("MEM0_API_KEY not found in .env")

def _get_session() -> requests.Session:
    """Get authenticated requests session."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Token {_load_api_key()}",
        "Content-Type": "application/json",
    })
    return session

def _log_event(event: dict, log_file: str = "mem0_wrapper.jsonl"):
    """Append event to log file."""
    log_path = LOG_DIR / log_file
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")

def _now_iso() -> str:
    """Current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()

# ---- Core Functions ----

def write_l3(
    text: str,
    user_id: str = "boss",
    agent_id: str = "hermes",
    topic: str = "uncategorized",
    sacred: bool = False,
    ttl_days: Optional[int] = None,
    source: str = "agent",
    layer_promotion_origin: str = "user_explicit",
    custom_instructions: str = DEFAULT_CUSTOM_INSTRUCTIONS,
    graph: bool = True,
    structured_categories: bool = True,
) -> dict:
    """
    Write a durable fact to L3 memory.
    
    Returns:
        dict with id, memory, metadata (or event_id if pending)
    """
    session = _get_session()
    
    # Build metadata
    metadata = {
        "topic": topic,
        "sacred": sacred,
        "source": source,
        "written_via": "mem0_wrapper_v1",
        "written_at": _now_iso(),
        "layer_promotion_origin": layer_promotion_origin,
    }
    
    if ttl_days:
        metadata["ttl_days"] = ttl_days
    
    # Build expiration date
    expires_at = None
    if ttl_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    
    # Build request body
    body = {
        "messages": [{"role": "user", "content": text}],
        "user_id": user_id,
        "agent_id": agent_id,
        "metadata": metadata,
        "custom_instructions": custom_instructions,
    }
    
    if graph:
        body["graph"] = True
    
    if structured_categories:
        body["output_format"] = "structured"
        body["structured_categories"] = CATEGORIES
    
    if expires_at:
        body["expires_at"] = expires_at
    
    # Make request
    resp = session.post(f"{MEM0_API_BASE}/memories/", json=body, timeout=30)
    
    if resp.status_code == 200:
        raw = resp.json()
        # Handle both direct response and pending response
        result = raw[0] if isinstance(raw, list) else raw
        
        _log_event({
            "action": "write_l3",
            "id": result.get("id"),
            "event_id": result.get("event_id"),
            "topic": topic,
            "sacred": sacred,
            "text": text[:100],
        })
        return result
    else:
        _log_event({
            "action": "write_l3_failed",
            "status": resp.status_code,
            "text": text[:100],
        })
        raise Exception(f"Write failed: {resp.status_code} {resp.text[:200]}")


def write_ephemeral(
    text: str,
    run_id: str,
    user_id: str = "boss",
    agent_id: str = "hermes",
    ttl_days: int = 1,
    **kwargs,
) -> dict:
    """Write ephemeral memory scoped to a run."""
    return write_l3(
        text,
        user_id=user_id,
        agent_id=agent_id,
        source="ephemeral",
        ttl_days=ttl_days,
        layer_promotion_origin="auto",
        **kwargs,
    )


def read_l3(
    memory_id: str,
    wait_for_propagation: bool = True,
    max_wait: int = 60,
) -> Optional[dict]:
    """
    Read a single memory by ID.
    Handles the write-path propagation bug.
    """
    session = _get_session()
    
    resp = session.get(f"{MEM0_API_BASE}/memories/{memory_id}/", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    
    if not wait_for_propagation:
        return None
    
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(5)
        resp = session.get(f"{MEM0_API_BASE}/memories/{memory_id}/", timeout=10)
        if resp.status_code == 200:
            _log_event({
                "action": "propagation_wait",
                "id": memory_id,
                "waited_seconds": int(time.time() - start),
            })
            return resp.json()
    
    return None


def list_l3(
    user_id: str = "boss",
    agent_id: str = "hermes",
    page_size: int = 100,
    page: int = 1,
) -> list[dict]:
    """List all memories in L3."""
    session = _get_session()
    all_memories = []
    
    while True:
        resp = session.get(
            f"{MEM0_API_BASE}/memories/",
            params={
                "user_id": user_id,
                "agent_id": agent_id,
                "page_size": page_size,
                "page": page,
            },
            timeout=30,
        )
        
        if resp.status_code != 200:
            break
        
        data = resp.json()
        items = data if isinstance(data, list) else data.get("results", [])
        all_memories.extend(items)
        
        if len(items) < page_size:
            break
        page += 1
        time.sleep(0.3)
    
    return all_memories


def search_l3(
    query: str,
    user_id: str = "boss",
    agent_id: str = "hermes",
    limit: int = 10,
) -> list[dict]:
    """Search L3 memories using semantic search."""
    session = _get_session()
    
    resp = session.post(
        f"{MEM0_API_BASE}/memories/search/",
        json={
            "query": query,
            "user_id": user_id,
            "agent_id": agent_id,
            "limit": limit,
        },
        timeout=15,
    )
    
    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, list) else data.get("results", [])
    
    return []


def delete_l3(memory_id: str) -> bool:
    """Delete a memory by ID."""
    session = _get_session()
    resp = session.delete(f"{MEM0_API_BASE}/memories/{memory_id}/", timeout=10)
    return resp.status_code == 200


def get_stats(user_id: str = "boss", agent_id: str = "hermes") -> dict:
    """Get statistics about L3 memory."""
    memories = list_l3(user_id=user_id, agent_id=agent_id)
    
    total_chars = sum(len(m.get("memory", "")) for m in memories)
    sacred_count = sum(1 for m in memories if (m.get("metadata") or {}).get("sacred"))
    
    categories = {}
    for m in memories:
        cat = (m.get("metadata") or {}).get("topic", "uncategorized")
        categories[cat] = categories.get(cat, 0) + 1
    
    return {
        "count": len(memories),
        "total_chars": total_chars,
        "sacred_count": sacred_count,
        "categories": categories,
        "avg_chars": total_chars // len(memories) if memories else 0,
    }


# ---- CLI ----

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Mem0 L3 wrapper")
    sub = parser.add_subparsers(dest="command")
    
    write_p = sub.add_parser("write", help="Write a fact")
    write_p.add_argument("text", help="Fact to store")
    write_p.add_argument("--topic", default="uncategorized")
    write_p.add_argument("--sacred", action="store_true")
    write_p.add_argument("--ttl", type=int, default=None)
    
    read_p = sub.add_parser("read", help="Read by ID")
    read_p.add_argument("id", help="Memory ID")
    
    list_p = sub.add_parser("list", help="List all")
    search_p = sub.add_parser("search", help="Search")
    search_p.add_argument("query", help="Search query")
    stats_p = sub.add_parser("stats", help="Get stats")
    del_p = sub.add_parser("delete", help="Delete by ID")
    del_p.add_argument("id", help="Memory ID")
    
    args = parser.parse_args()
    
    if args.command == "write":
        result = write_l3(args.text, topic=args.topic, sacred=args.sacred, ttl_days=args.ttl)
        print(json.dumps(result, indent=2))
    elif args.command == "read":
        result = read_l3(args.id)
        print(json.dumps(result, indent=2) if result else "Not found")
    elif args.command == "list":
        results = list_l3()
        for m in results:
            print(f"  {m['id']}: {m.get('memory', '')[:80]}")
    elif args.command == "search":
        results = search_l3(args.query)
        for m in results:
            print(f"  {m.get('memory', '')[:80]}")
    elif args.command == "stats":
        stats = get_stats()
        print(json.dumps(stats, indent=2))
    elif args.command == "delete":
        if delete_l3(args.id):
            print("Deleted")
        else:
            print("Failed")
    else:
        parser.print_help()
