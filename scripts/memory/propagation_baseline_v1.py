#!/usr/bin/env python3
"""LOOP-5: Re-baseline mem0 write-path propagation bug.

Tests the write-read-search propagation cycle.
The mem0 API returns a PENDING status on write, so we must wait for processing.
"""
import json, time, sys
sys.path.insert(0, "/root/.hermes/scripts")
from datetime import datetime, timezone
from mem0_wrapper_v1 import write_l3, read_l3, list_l3, delete_l3, _log_event, search_l3, _get_session, _load_api_key, MEM0_API_BASE

def wait_for_entry(event_id, max_wait=120):
    """Wait for a pending write to be fully processed."""
    session = _get_session()
    start = time.time()
    while time.time() - start < max_wait:
        resp = session.post(
            f"{MEM0_API_BASE}/memories/status/",
            json={"event_id": event_id},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "completed":
                return data.get("memory_id")
            elif data.get("status") == "failed":
                return None
        time.sleep(3)
    return None

def test_propagation():
    """POST 3 test entries, measure propagation lag."""
    results = []
    entry_ids = []
    
    for i in range(3):
        entry = write_l3(
            f"Propagation test {i+1} at {datetime.now(timezone.utc).isoformat()}",
            topic="test",
            source="propagation_test",
        )
        eid = entry.get("id")
        event_id = entry.get("event_id")
        
        if eid:
            entry_ids.append(eid)
            results.append({"id": eid, "written_at": datetime.now(timezone.utc).isoformat()})
        elif event_id:
            # Wait for processing
            memory_id = wait_for_entry(event_id)
            if memory_id:
                entry_ids.append(memory_id)
                results.append({"id": memory_id, "written_at": datetime.now(timezone.utc).isoformat()})
            else:
                print(f"  Write {i+1} timed out: event_id={event_id}")
        else:
            print(f"  Write {i+1} returned: {entry}")
    
    time.sleep(2)
    
    for entry in results:
        eid = entry["id"]
        direct = read_l3(eid, wait_for_propagation=False)
        entry["direct_get"] = direct is not None
        
        all_mems = list_l3()
        entry["in_list"] = any(m["id"] == eid for m in all_mems)
        
        search_results = search_l3("Propagation test")
        entry["in_search"] = any(m.get("id") == eid for m in search_results)
        
        print(f"  {eid[:12]}... direct={entry['direct_get']} list={entry['in_list']} search={entry['in_search']}")
    
    for eid in entry_ids:
        delete_l3(eid)
    
    _log_event({"action": "propagation_baseline", "results": results})
    return results

if __name__ == "__main__":
    print("Testing propagation...")
    results = test_propagation()
    print(f"\nResults: {json.dumps(results, indent=2)}")
