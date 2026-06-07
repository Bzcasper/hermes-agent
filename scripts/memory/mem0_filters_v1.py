from __future__ import annotations
#!/usr/bin/env python3
import sys; sys.path.insert(0, "/root/.hermes/scripts")
"""
mem0_filters_v1.py — V2 filter helpers for L3 memory.

Centralizes filter logic used by audit, status, budget probe scripts.

Usage:
    from mem0_filters_v1 import filter_by_topic, filter_by_sacred, filter_by_date
    
    # Filter memories
    sacred = filter_by_sacred(memories)
    recent = filter_by_date(memories, days=7)
"""
from typing import Any
from datetime import datetime, timezone, timedelta


def filter_by_topic(memories: list[dict], topic: str) -> list[dict]:
    """Filter memories by topic category."""
    return [
        m for m in memories
        if (m.get("metadata") or {}).get("topic") == topic
    ]


def filter_by_sacred(memories: list[dict]) -> list[dict]:
    """Filter sacred memories (never auto-pruned)."""
    return [
        m for m in memories
        if (m.get("metadata") or {}).get("sacred") is True
    ]


def filter_by_date(
    memories: list[dict],
    days: int = 7,
    after: bool = True,
) -> list[dict]:
    """Filter memories by date (created_at)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = []
    for m in memories:
        created = m.get("created_at")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if after and dt >= cutoff:
                result.append(m)
            elif not after and dt < cutoff:
                result.append(m)
        except (ValueError, TypeError):
            continue
    return result


def filter_by_agent(memories: list[dict], agent_id: str) -> list[dict]:
    """Filter memories by agent_id."""
    return [
        m for m in memories
        if m.get("agent_id") == agent_id
    ]


def filter_by_source(memories: list[dict], source: str) -> list[dict]:
    """Filter memories by source."""
    return [
        m for m in memories
        if (m.get("metadata") or {}).get("source") == source
    ]


def filter_by_char_limit(memories: list[dict], limit: int = 2200) -> list[dict]:
    """Filter memories exceeding char limit."""
    return [
        m for m in memories
        if len(m.get("memory", "")) > limit
    ]


def get_injection_budget(memories: list[dict], limit: int = 5000) -> dict:
    """
    Calculate injection budget.
    
    Returns:
        dict with total_chars, over_budget, top_10_chars, top_20_chars
    """
    sorted_mems = sorted(memories, key=lambda m: len(m.get("memory", "")), reverse=True)
    
    total_chars = sum(len(m.get("memory", "")) for m in memories)
    top_10_chars = sum(len(m.get("memory", "")) for m in sorted_mems[:10])
    top_20_chars = sum(len(m.get("memory", "")) for m in sorted_mems[:20])
    
    return {
        "total_chars": total_chars,
        "over_budget": total_chars > limit,
        "budget": limit,
        "top_10_chars": top_10_chars,
        "top_10_under_budget": top_10_chars <= limit,
        "top_20_chars": top_20_chars,
        "top_20_under_budget": top_20_chars <= limit,
    }


def get_category_distribution(memories: list[dict]) -> dict:
    """Get distribution of topics/categories."""
    dist = {}
    for m in memories:
        cat = (m.get("metadata") or {}).get("topic", "uncategorized")
        dist[cat] = dist.get(cat, 0) + 1
    return dist


if __name__ == "__main__":
    import json
    from mem0_wrapper_v1 import list_l3
    
    memories = list_l3()
    print(f"Total: {len(memories)}")
    
    budget = get_injection_budget(memories)
    print(f"Budget: {json.dumps(budget, indent=2)}")
    
    dist = get_category_distribution(memories)
    print(f"Categories: {json.dumps(dist, indent=2)}")
    
    sacred = filter_by_sacred(memories)
    print(f"Sacred: {len(sacred)}")
