#!/usr/bin/env python3
"""P3.3: Async client wrapper for batch operations."""
import json, asyncio, time
from typing import List, Dict
from mem0_wrapper_v1 import _get_session, MEM0_API_BASE, _log_event

async def batch_write(entries: List[Dict], concurrency: int = 5):
    """Write multiple entries concurrently."""
    session = _get_session()
    semaphore = asyncio.Semaphore(concurrency)
    
    async def write_one(entry):
        async with semaphore:
            # Use sync session in thread
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: session.post(
                f"{MEM0_API_BASE}/memories/",
                json=entry,
                timeout=30,
            ))
    
    tasks = [write_one(e) for e in entries]
    await asyncio.gather(*tasks)
    return len(entries)

def batch_write_sync(entries: List[Dict]) -> int:
    """Sync wrapper for batch writes."""
    return asyncio.run(batch_write(entries))

if __name__ == "__main__":
    print("Async batch write wrapper ready")
