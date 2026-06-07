#!/usr/bin/env python3
import sys; sys.path.insert(0, "/root/.hermes/scripts")
"""Memory health check - audit + dashboard + self-test."""
import json, sys
from pathlib import Path
from mem0_wrapper_v1 import list_l3, get_stats
from mem0_filters_v1 import get_injection_budget, get_category_distribution, filter_by_sacred

def health_check():
    """Run full health check."""
    memories = list_l3()
    stats = get_stats()
    budget = get_injection_budget(memories)
    dist = get_category_distribution(memories)
    sacred = filter_by_sacred(memories)
    
    report = {
        "status": "healthy" if not budget["over_budget"] else "warning",
        "total_entries": stats["count"],
        "total_chars": stats["total_chars"],
        "budget": budget,
        "categories": dist,
        "sacred_count": len(sacred),
    }
    
    return report

if __name__ == "__main__":
    report = health_check()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["status"] == "healthy" else 1)
