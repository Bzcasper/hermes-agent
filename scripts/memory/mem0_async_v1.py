#!/usr/bin/env python3
"""P3.3: Async client wrapper for batch operations."""
import json, asyncio, time, threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict
from mem0_wrapper_v1 import _get_session, MEM0_API_BASE, _log_event


def _write_one(entry: Dict) -> Dict:
    """Write a single entry with its own session (thread-safe)."""
    session = _get_session()
    try:
        resp = session.post(f"{MEM0_API_BASE}/memories/", json=entry, timeout=30)
        raw = resp.json()
        return {"status": resp.status_code, "response": raw}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def batch_write_sync(entries: List[Dict], concurrency: int = 5) -> int:
    """Write multiple entries concurrently (thread-safe)."""
    if not entries:
        return 0
    
    semaphore = threading.Semaphore(concurrency)
    
    def limited_write(entry):
        with semaphore:
            return _write_one(entry)
    
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(limited_write, e) for e in entries]
        for f in futures:
            results.append(f.result())
    
    success = sum(1 for r in results if r.get("status") == 200)
    failed = len(results) - success
    
    if failed:
        _log_event({"action": "batch_write", "success": success, "failed": failed})
    
    return success


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    print("Async batch write wrapper ready")
