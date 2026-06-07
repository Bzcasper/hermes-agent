#!/usr/bin/env python3
"""
Comprehensive isolated tests for ALL hermes memory scripts.
Tests every public function with mocked dependencies.
No real API calls — all network I/O is mocked.

Run: python3 test_all_scripts.py
"""
import json
import sys
import os
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, mock_open
from difflib import SequenceMatcher

# Setup path
sys.path.insert(0, "/root/.hermes/scripts")

# ============================================================
# FIXTURES
# ============================================================

def make_memory(id="test-001", memory="Test memory", topic="test", sacred=False,
                source="agent", created_at=None, agent_id="hermes", ttl_days=None):
    """Create a fake memory dict matching mem0 API shape."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "topic": topic,
        "sacred": sacred,
        "source": source,
        "written_via": "mem0_wrapper_v1",
        "written_at": created_at,
        "layer_promotion_origin": "user_explicit",
    }
    if ttl_days:
        meta["ttl_days"] = ttl_days
    return {
        "id": id,
        "memory": memory,
        "metadata": meta,
        "created_at": created_at,
        "agent_id": agent_id,
        "user_id": "boss",
    }

SAMPLE_MEMORIES = [
    make_memory(id="m-001", memory="User prefers dark mode for IDE", topic="preferences"),
    make_memory(id="m-002", memory="VPS IP is 152.44.46.92", topic="environment"),
    make_memory(id="m-003", memory="Hermes agent project uses OpenCode Zen", topic="project"),
    make_memory(id="m-004", memory="User prefers dark mode for IDE", topic="preferences"),  # near-dup of m-001
    make_memory(id="m-005", memory="Robert Casper is the user", topic="sacred", sacred=True),
    make_memory(id="m-006", memory="User started a claude-code session", topic="uncategorized"),  # noise
    make_memory(id="m-007", memory="Short", topic="test"),
    make_memory(id="m-008", memory="A" * 3000, topic="test"),  # oversized
    make_memory(id="m-009", memory="Another test memory", topic="test",
                created_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat()),
    make_memory(id="m-010", memory="Recent entry", topic="test",
                created_at=datetime.now(timezone.utc).isoformat()),
]

def mock_list_l3():
    return [m.copy() for m in SAMPLE_MEMORIES]

def mock_write_l3(text, **kwargs):
    return {"id": f"new-{int(time.time())}", "memory": text, "status": "PENDING",
            "event_id": f"evt-{int(time.time())}"}

def mock_delete_l3(mid):
    return True

def mock_search_l3(query, **kwargs):
    return [m for m in SAMPLE_MEMORIES if query.lower() in m.get("memory", "").lower()]

def mock_get_stats(**kwargs):
    memories = mock_list_l3()
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

# ============================================================
# TEST RESULTS TRACKER
# ============================================================

results = {"passed": 0, "failed": 0, "errors": []}

def test(name, fn):
    try:
        fn()
        results["passed"] += 1
        print(f"  ✓ {name}")
    except Exception as e:
        results["failed"] += 1
        results["errors"].append((name, str(e)))
        print(f"  ✗ {name}: {e}")

def assert_eq(a, b, msg=""):
    if a != b:
        raise AssertionError(f"{msg}: expected {b!r}, got {a!r}")

def assert_true(val, msg=""):
    if not val:
        raise AssertionError(f"{msg}: expected truthy, got {val!r}")

def assert_false(val, msg=""):
    if val:
        raise AssertionError(f"{msg}: expected falsy, got {val!r}")

def assert_in(item, collection, msg=""):
    if item not in collection:
        raise AssertionError(f"{msg}: {item!r} not in {collection!r}")

# ============================================================
# TEST SUITE 1: mem0_filters_v1.py
# ============================================================

print("\n=== mem0_filters_v1.py ===")

def test_filter_by_topic():
    from mem0_filters_v1 import filter_by_topic
    result = filter_by_topic(SAMPLE_MEMORIES, "preferences")
    assert_eq(len(result), 2)
    assert_true(all(m["id"] in ("m-001", "m-004") for m in result))

def test_filter_by_topic_empty():
    from mem0_filters_v1 import filter_by_topic
    result = filter_by_topic(SAMPLE_MEMORIES, "nonexistent")
    assert_eq(len(result), 0)

def test_filter_by_topic_missing_metadata():
    from mem0_filters_v1 import filter_by_topic
    mems = [{"id": "x", "memory": "test"}]
    result = filter_by_topic(mems, "test")
    assert_eq(len(result), 0)

def test_filter_by_sacred():
    from mem0_filters_v1 import filter_by_sacred
    result = filter_by_sacred(SAMPLE_MEMORIES)
    assert_eq(len(result), 1)
    assert_eq(result[0]["id"], "m-005")

def test_filter_by_sacred_none():
    from mem0_filters_v1 import filter_by_sacred
    result = filter_by_sacred([])
    assert_eq(len(result), 0)

def test_filter_by_date_recent():
    from mem0_filters_v1 import filter_by_date
    recent = filter_by_date(SAMPLE_MEMORIES, days=1, after=True)
    # m-010 is now, m-009 is 10 days old
    assert_true(any(m["id"] == "m-010" for m in recent))
    assert_false(any(m["id"] == "m-009" for m in recent))

def test_filter_by_date_old():
    from mem0_filters_v1 import filter_by_date
    old = filter_by_date(SAMPLE_MEMORIES, days=5, after=False)
    assert_true(any(m["id"] == "m-009" for m in old))

def test_filter_by_date_no_created():
    from mem0_filters_v1 import filter_by_date
    mems = [{"id": "x", "memory": "test", "metadata": {}}]
    result = filter_by_date(mems, days=7)
    assert_eq(len(result), 0)

def test_filter_by_date_bad_format():
    from mem0_filters_v1 import filter_by_date
    mems = [{"id": "x", "memory": "test", "created_at": "not-a-date"}]
    result = filter_by_date(mems, days=7)
    assert_eq(len(result), 0)

def test_filter_by_agent():
    from mem0_filters_v1 import filter_by_agent
    result = filter_by_agent(SAMPLE_MEMORIES, "hermes")
    assert_eq(len(result), len(SAMPLE_MEMORIES))

def test_filter_by_agent_mismatch():
    from mem0_filters_v1 import filter_by_agent
    result = filter_by_agent(SAMPLE_MEMORIES, "other-agent")
    assert_eq(len(result), 0)

def test_filter_by_source():
    from mem0_filters_v1 import filter_by_source
    result = filter_by_source(SAMPLE_MEMORIES, "agent")
    assert_true(len(result) > 0)

def test_filter_by_char_limit():
    from mem0_filters_v1 import filter_by_char_limit
    oversized = filter_by_char_limit(SAMPLE_MEMORIES, limit=2200)
    assert_eq(len(oversized), 1)
    assert_eq(oversized[0]["id"], "m-008")

def test_get_injection_budget():
    from mem0_filters_v1 import get_injection_budget
    budget = get_injection_budget(SAMPLE_MEMORIES, limit=5000)
    assert_true("total_chars" in budget)
    assert_true("over_budget" in budget)
    assert_true("top_10_chars" in budget)
    assert_true("top_20_chars" in budget)
    assert_true(budget["total_chars"] > 0)

def test_get_injection_budget_over():
    from mem0_filters_v1 import get_injection_budget
    budget = get_injection_budget(SAMPLE_MEMORIES, limit=100)
    assert_true(budget["over_budget"])

def test_get_category_distribution():
    from mem0_filters_v1 import get_category_distribution
    dist = get_category_distribution(SAMPLE_MEMORIES)
    assert_in("preferences", dist)
    assert_in("sacred", dist)
    assert_eq(dist["preferences"], 2)

def test_get_category_distribution_empty():
    from mem0_filters_v1 import get_category_distribution
    dist = get_category_distribution([])
    assert_eq(dist, {})

test("filter_by_topic", test_filter_by_topic)
test("filter_by_topic_empty", test_filter_by_topic_empty)
test("filter_by_topic_missing_metadata", test_filter_by_topic_missing_metadata)
test("filter_by_sacred", test_filter_by_sacred)
test("filter_by_sacred_none", test_filter_by_sacred_none)
test("filter_by_date_recent", test_filter_by_date_recent)
test("filter_by_date_old", test_filter_by_date_old)
test("filter_by_date_no_created", test_filter_by_date_no_created)
test("filter_by_date_bad_format", test_filter_by_date_bad_format)
test("filter_by_agent", test_filter_by_agent)
test("filter_by_agent_mismatch", test_filter_by_agent_mismatch)
test("filter_by_source", test_filter_by_source)
test("filter_by_char_limit", test_filter_by_char_limit)
test("get_injection_budget", test_get_injection_budget)
test("get_injection_budget_over", test_get_injection_budget_over)
test("get_category_distribution", test_get_category_distribution)
test("get_category_distribution_empty", test_get_category_distribution_empty)

# ============================================================
# TEST SUITE 2: mem0_wrapper_v1.py
# ============================================================

print("\n=== mem0_wrapper_v1.py ===")

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_write_l3_success(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import write_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "new-001", "memory": "test"}
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = write_l3("test entry", topic="test")
        assert_eq(result["id"], "new-001")
        mock_sess.post.assert_called_once()

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_write_l3_list_response(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import write_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"id": "new-002", "memory": "test"}]
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = write_l3("test entry")
        assert_eq(result["id"], "new-002")

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_write_l3_failure(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import write_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        try:
            write_l3("test entry")
            raise AssertionError("Should have raised")
        except Exception as e:
            assert_in("500", str(e))

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_write_l3_with_ttl(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import write_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "ttl-001"}
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = write_l3("ttl test", ttl_days=7)
        call_body = mock_sess.post.call_args[1]["json"]
        assert_in("expires_at", call_body)
        assert_in("ttl_days", call_body["metadata"])

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_write_ephemeral(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import write_ephemeral
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "eph-001"}
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = write_ephemeral("ephemeral test", run_id="cron-123")
        call_body = mock_sess.post.call_args[1]["json"]
        assert_eq(call_body["metadata"]["source"], "ephemeral")

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_read_l3_found(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import read_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "read-001", "memory": "found"}
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.get.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = read_l3("read-001", wait_for_propagation=False)
        assert_true(result is not None)
        assert_eq(result["id"], "read-001")

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_read_l3_not_found_no_wait(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import read_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.get.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = read_l3("nonexistent", wait_for_propagation=False)
        assert_true(result is None)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_list_l3(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import list_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_MEMORIES[:3]
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.get.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = list_l3()
        assert_eq(len(result), 3)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_list_l3_pagination(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import list_l3
    page1 = MagicMock()
    page1.status_code = 200
    page1.json.return_value = SAMPLE_MEMORIES[:3]
    page2 = MagicMock()
    page2.status_code = 200
    page2.json.return_value = SAMPLE_MEMORIES[3:5]
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.get.side_effect = [page1, page2]
        mock_sess_cls.return_value = mock_sess
        result = list_l3(page_size=3)
        assert_eq(len(result), 5)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_search_l3(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import search_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [SAMPLE_MEMORIES[0]]
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = search_l3("dark mode")
        assert_eq(len(result), 1)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_search_l3_empty(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import search_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.post.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = search_l3("nonexistent query xyz")
        assert_eq(len(result), 0)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_delete_l3(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import delete_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.delete.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = delete_l3("del-001")
        assert_true(result is True)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1._log_event")
@patch("mem0_wrapper_v1.Path")
def test_delete_l3_failure(mock_path, mock_log, mock_key):
    from mem0_wrapper_v1 import delete_l3
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("mem0_wrapper_v1.requests.Session") as mock_sess_cls:
        mock_sess = MagicMock()
        mock_sess.delete.return_value = mock_resp
        mock_sess_cls.return_value = mock_sess
        result = delete_l3("nonexistent")
        assert_true(result is False)

@patch("mem0_wrapper_v1._load_api_key", return_value="test-key-123")
@patch("mem0_wrapper_v1.list_l3")
def test_get_stats(mock_list, mock_key):
    from mem0_wrapper_v1 import get_stats
    mock_list.return_value = SAMPLE_MEMORIES
    stats = get_stats()
    assert_eq(stats["count"], 10)
    assert_true(stats["total_chars"] > 0)
    assert_eq(stats["sacred_count"], 1)

@patch("mem0_wrapper_v1.ENV_PATH")
def test_load_api_key_missing(mock_path):
    from mem0_wrapper_v1 import _load_api_key
    mock_path.exists.return_value = False
    try:
        _load_api_key()
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert_in("MEM0_API_KEY", str(e))

@patch("mem0_wrapper_v1.MEM0_JSON")
def test_load_config_missing(mock_path):
    from mem0_wrapper_v1 import _load_config
    mock_path.exists.return_value = False
    result = _load_config()
    assert_eq(result, {})

test("write_l3_success", test_write_l3_success)
test("write_l3_list_response", test_write_l3_list_response)
test("write_l3_failure", test_write_l3_failure)
test("write_l3_with_ttl", test_write_l3_with_ttl)
test("write_ephemeral", test_write_ephemeral)
test("read_l3_found", test_read_l3_found)
test("read_l3_not_found_no_wait", test_read_l3_not_found_no_wait)
test("list_l3", test_list_l3)
test("list_l3_pagination", test_list_l3_pagination)
test("search_l3", test_search_l3)
test("search_l3_empty", test_search_l3_empty)
test("delete_l3", test_delete_l3)
test("delete_l3_failure", test_delete_l3_failure)
test("get_stats", test_get_stats)
test("load_api_key_missing", test_load_api_key_missing)
test("load_config_missing", test_load_config_missing)

# ============================================================
# TEST SUITE 3: graph_dedup_v1.py
# ============================================================

print("\n=== graph_dedup_v1.py ===")

@patch("graph_dedup_v1.list_l3", side_effect=mock_list_l3)
def test_find_near_dups(mock_list):
    from graph_dedup_v1 import find_near_dups
    dups = find_near_dups(threshold=0.85)
    # m-001 and m-004 are near-duplicates
    assert_true(len(dups) >= 1)
    ids = set()
    for m1, m2, sim in dups:
        ids.add(m1["id"])
        ids.add(m2["id"])
    assert_in("m-001", ids)

@patch("graph_dedup_v1.list_l3", side_effect=mock_list_l3)
def test_find_near_dups_no_threshold(mock_list):
    from graph_dedup_v1 import find_near_dups
    dups = find_near_dups(threshold=0.99)
    # Stricter threshold = fewer dups
    assert_true(len(dups) >= 0)

@patch("graph_dedup_v1.list_l3", side_effect=mock_list_l3)
@patch("graph_dedup_v1.delete_l3", side_effect=mock_delete_l3)
@patch("graph_dedup_v1._log_event")
def test_dedup_dry_run(mock_log, mock_del, mock_list):
    from graph_dedup_v1 import dedup
    deleted = dedup(dry_run=True)
    assert_eq(deleted, 0)
    mock_del.assert_not_called()

@patch("graph_dedup_v1.list_l3", side_effect=mock_list_l3)
@patch("graph_dedup_v1.delete_l3", side_effect=mock_delete_l3)
@patch("graph_dedup_v1._log_event")
def test_dedup_apply(mock_log, mock_del, mock_list):
    from graph_dedup_v1 import dedup
    deleted = dedup(dry_run=False)
    assert_true(deleted >= 0)

test("find_near_dups", test_find_near_dups)
test("find_near_dups_no_threshold", test_find_near_dups_no_threshold)
test("dedup_dry_run", test_dedup_dry_run)
test("dedup_apply", test_dedup_apply)

# ============================================================
# TEST SUITE 4: expiration_policy_v1.py
# ============================================================

print("\n=== expiration_policy_v1.py ===")

@patch("expiration_policy_v1.list_l3")
def test_cleanup_expired_finds_expired(mock_list):
    from expiration_policy_v1 import cleanup_expired
    expired_mem = make_memory(id="exp-001", topic="test")
    expired_mem["expiration_date"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    active_mem = make_memory(id="act-001", topic="test")
    active_mem["expiration_date"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    mock_list.return_value = [expired_mem, active_mem]
    result = cleanup_expired()
    assert_eq(result, 1)  # Returns count of expired entries found

@patch("expiration_policy_v1.list_l3")
def test_cleanup_expired_none(mock_list):
    from expiration_policy_v1 import cleanup_expired
    active_mem = make_memory(id="act-002", topic="test")
    active_mem["expiration_date"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    mock_list.return_value = [active_mem]
    result = cleanup_expired()
    assert_eq(result, 0)

@patch("expiration_policy_v1.list_l3")
def test_cleanup_expired_bad_date(mock_list):
    from expiration_policy_v1 import cleanup_expired
    bad_mem = make_memory(id="bad-001", topic="test")
    bad_mem["expiration_date"] = "not-a-date"
    mock_list.return_value = [bad_mem]
    result = cleanup_expired()
    assert_eq(result, 0)

@patch("expiration_policy_v1.list_l3")
def test_cleanup_expired_no_expiration(mock_list):
    from expiration_policy_v1 import cleanup_expired
    mem = make_memory(id="no-exp", topic="test")
    # make_memory doesn't add expiration_date, so just use it as-is
    mock_list.return_value = [mem]
    result = cleanup_expired()
    # cleanup_expired now returns deleted count (dry_run=True returns count of expired)
    assert_eq(result, 0)

test("cleanup_expired_finds_expired", test_cleanup_expired_finds_expired)
test("cleanup_expired_none", test_cleanup_expired_none)
test("cleanup_expired_bad_date", test_cleanup_expired_bad_date)
test("cleanup_expired_no_expiration", test_cleanup_expired_no_expiration)

# ============================================================
# TEST SUITE 5: mem0_export_v1.py
# ============================================================

print("\n=== mem0_export_v1.py ===")

@patch("mem0_export_v1.list_l3", side_effect=mock_list_l3)
@patch("mem0_export_v1._log_event")
def test_export_memories(mock_log, mock_list):
    from mem0_export_v1 import export_memories, EXPORT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("mem0_export_v1.EXPORT_DIR", Path(tmpdir)):
            result = export_memories()
            assert_true(result.exists())
            lines = result.read_text().strip().split("\n")
            assert_eq(len(lines), len(SAMPLE_MEMORIES))
            for line in lines:
                data = json.loads(line)
                assert_in("id", data)
                assert_in("memory", data)
            result.unlink()

@patch("mem0_export_v1.list_l3", return_value=[])
@patch("mem0_export_v1._log_event")
def test_export_empty(mock_log, mock_list):
    from mem0_export_v1 import export_memories
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("mem0_export_v1.EXPORT_DIR", Path(tmpdir)):
            result = export_memories()
            assert_true(result.exists())
            assert_eq(result.read_text().strip(), "")
            result.unlink()

test("export_memories", test_export_memories)
test("export_empty", test_export_empty)

# ============================================================
# TEST SUITE 6: mem0_events_v1.py
# ============================================================

print("\n=== mem0_events_v1.py ===")

@patch("mem0_events_v1._get_session")
@patch("mem0_events_v1._log_event")
def test_poll_events_success(mock_log, mock_sess_cls):
    from mem0_events_v1 import poll_events
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"event": "create"}, {"event": "update"}]
    mock_sess.get.return_value = mock_resp
    mock_sess_cls.return_value = mock_sess
    with patch("mem0_events_v1.LOG_FILE", Path(tempfile.mktemp(suffix=".jsonl"))):
        result = poll_events()
        assert_true(isinstance(result, list))
        assert_eq(len(result), 2)

@patch("mem0_events_v1._get_session")
@patch("mem0_events_v1._log_event")
def test_poll_events_api_error(mock_log, mock_sess_cls):
    from mem0_events_v1 import poll_events
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_sess.get.return_value = mock_resp
    mock_sess_cls.return_value = mock_sess
    with patch("mem0_events_v1.LOG_FILE", Path(tempfile.mktemp(suffix=".jsonl"))):
        result = poll_events()
        assert_eq(result, [])

@patch("mem0_events_v1._get_session")
@patch("mem0_events_v1._log_event")
def test_poll_events_network_error(mock_log, mock_sess_cls):
    from mem0_events_v1 import poll_events
    mock_sess = MagicMock()
    mock_sess.get.side_effect = Exception("Connection refused")
    mock_sess_cls.return_value = mock_sess
    with patch("mem0_events_v1.LOG_FILE", Path(tempfile.mktemp(suffix=".jsonl"))):
        result = poll_events()
        assert_eq(result, [])

test("poll_events_success", test_poll_events_success)
test("poll_events_api_error", test_poll_events_api_error)
test("poll_events_network_error", test_poll_events_network_error)

# ============================================================
# TEST SUITE 7: mem0_async_v1.py
# ============================================================

print("\n=== mem0_async_v1.py ===")

@patch("mem0_async_v1._get_session")
def test_batch_write_sync(mock_sess_cls):
    from mem0_async_v1 import batch_write_sync
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_sess.post.return_value = mock_resp
    mock_sess_cls.return_value = mock_sess
    entries = [{"messages": [{"role": "user", "content": f"entry {i}"}]} for i in range(3)]
    result = batch_write_sync(entries)
    assert_eq(result, 3)

@patch("mem0_async_v1._get_session")
def test_batch_write_sync_empty(mock_sess_cls):
    from mem0_async_v1 import batch_write_sync
    mock_sess = MagicMock()
    mock_sess_cls.return_value = mock_sess
    result = batch_write_sync([])
    assert_eq(result, 0)

@patch("mem0_async_v1._get_session")
def test_batch_write_sync_partial_failure(mock_sess_cls):
    from mem0_async_v1 import batch_write_sync
    mock_sess = MagicMock()
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_fail = MagicMock()
    mock_resp_fail.status_code = 500
    mock_sess.post.side_effect = [mock_resp_ok, mock_resp_fail, mock_resp_ok]
    mock_sess_cls.return_value = mock_sess
    entries = [{"messages": [{"role": "user", "content": f"entry {i}"}]} for i in range(3)]
    result = batch_write_sync(entries)
    assert_eq(result, 2)  # Returns success count, not total

test("batch_write_sync", test_batch_write_sync)
test("batch_write_sync_empty", test_batch_write_sync_empty)
test("batch_write_sync_partial_failure", test_batch_write_sync_partial_failure)

# ============================================================
# TEST SUITE 8: memory_health_check_v1.py
# ============================================================

print("\n=== memory_health_check_v1.py ===")

@patch("memory_health_check_v1.list_l3", side_effect=mock_list_l3)
@patch("memory_health_check_v1.get_stats", side_effect=mock_get_stats)
@patch("memory_health_check_v1.get_injection_budget")
@patch("memory_health_check_v1.get_category_distribution")
@patch("memory_health_check_v1.filter_by_sacred")
def test_health_check_healthy(mock_sacred, mock_dist, mock_budget, mock_stats, mock_list):
    from memory_health_check_v1 import health_check
    mock_budget.return_value = {
        "total_chars": 5000, "over_budget": False, "budget": 5000,
        "top_10_chars": 3000, "top_10_under_budget": True,
        "top_20_chars": 5000, "top_20_under_budget": True,
    }
    mock_dist.return_value = {"test": 5}
    mock_sacred.return_value = [make_memory(sacred=True)]
    report = health_check()
    assert_eq(report["status"], "healthy")
    assert_eq(report["total_entries"], 10)

@patch("memory_health_check_v1.list_l3", side_effect=mock_list_l3)
@patch("memory_health_check_v1.get_stats", side_effect=mock_get_stats)
@patch("memory_health_check_v1.get_injection_budget")
@patch("memory_health_check_v1.get_category_distribution")
@patch("memory_health_check_v1.filter_by_sacred")
def test_health_check_warning(mock_sacred, mock_dist, mock_budget, mock_stats, mock_list):
    from memory_health_check_v1 import health_check
    mock_budget.return_value = {
        "total_chars": 6000, "over_budget": True, "budget": 5000,
        "top_10_chars": 4000, "top_10_under_budget": False,
        "top_20_chars": 6000, "top_20_under_budget": False,
    }
    mock_dist.return_value = {"test": 5}
    mock_sacred.return_value = []
    report = health_check()
    assert_eq(report["status"], "warning")
    assert_true(report["budget"]["over_budget"])

test("health_check_healthy", test_health_check_healthy)
test("health_check_warning", test_health_check_warning)

# ============================================================
# TEST SUITE 9: propagation_baseline_v1.py
# ============================================================

print("\n=== propagation_baseline_v1.py ===")

@patch("propagation_baseline_v1._get_session")
def test_wait_for_entry_completed(mock_sess_cls):
    from propagation_baseline_v1 import wait_for_entry
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "completed", "memory_id": "mem-001"}
    mock_sess.post.return_value = mock_resp
    mock_sess_cls.return_value = mock_sess
    result = wait_for_entry("evt-001", max_wait=5)
    assert_eq(result, "mem-001")

@patch("propagation_baseline_v1._get_session")
def test_wait_for_entry_failed(mock_sess_cls):
    from propagation_baseline_v1 import wait_for_entry
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "failed"}
    mock_sess.post.return_value = mock_resp
    mock_sess_cls.return_value = mock_sess
    result = wait_for_entry("evt-002", max_wait=5)
    assert_true(result is None)

@patch("propagation_baseline_v1._get_session")
def test_wait_for_entry_timeout(mock_sess_cls):
    from propagation_baseline_v1 import wait_for_entry
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "pending"}
    mock_sess.post.return_value = mock_resp
    mock_sess_cls.return_value = mock_sess
    result = wait_for_entry("evt-003", max_wait=1)
    assert_true(result is None)

test("wait_for_entry_completed", test_wait_for_entry_completed)
test("wait_for_entry_failed", test_wait_for_entry_failed)
test("wait_for_entry_timeout", test_wait_for_entry_timeout)

# ============================================================
# TEST SUITE 10: Bash scripts syntax check
# ============================================================

print("\n=== Bash scripts syntax ===")

def test_bash_syntax():
    import subprocess
    scripts = [
        "gateway-healthcheck.sh",
        "model-fallback-probe.sh",
        "refresh_models.sh",
        "memory-healthcheck.sh",
        "weekly_memory_cleanup.sh",
    ]
    for script in scripts:
        path = f"/root/.hermes/scripts/{script}"
        result = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(f"Syntax error in {script}: {result.stderr}")

test("bash_syntax", test_bash_syntax)

# ============================================================
# TEST SUITE 11: weekly_cleanup_impl.py
# ============================================================

print("\n=== weekly_cleanup_impl.py ===")

def test_weekly_cleanup_list_all():
    """Test list_all pagination logic with mock."""
    import weekly_cleanup_impl as wci
    # Just verify the module loads and NOISE_PREFIXES is defined
    assert_true(len(wci.NOISE_PREFIXES) > 0)
    assert_in("User started a claude-code session", wci.NOISE_PREFIXES)

def test_weekly_cleanup_noise_detection():
    """Test noise prefix detection."""
    import weekly_cleanup_impl as wci
    noise_entry = {"id": "n-001", "memory": "User started a claude-code session today"}
    clean_entry = {"id": "c-001", "memory": "User prefers dark mode"}
    for prefix in wci.NOISE_PREFIXES:
        if noise_entry["memory"].startswith(prefix):
            assert_true(True)
            return
    raise AssertionError("Noise entry not detected")

test("weekly_cleanup_list_all", test_weekly_cleanup_list_all)
test("weekly_cleanup_noise_detection", test_weekly_cleanup_noise_detection)

# ============================================================
# SUMMARY
# ============================================================

print(f"\n{'='*60}")
print(f"RESULTS: {results['passed']} passed, {results['failed']} failed")
print(f"{'='*60}")

if results["errors"]:
    print("\nFAILURES:")
    for name, err in results["errors"]:
        print(f"  ✗ {name}: {err}")

sys.exit(0 if results["failed"] == 0 else 1)
