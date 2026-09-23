#!/usr/bin/env python
"""Aetheris Core — end-to-end smoke test against the orchestrator.

Usage:
    python scripts/smoke_test.py [--orchestrator http://127.0.0.1:8000]

Validates: health -> corpus stats -> SSE agent run (route/retrieve/rerank/grade/
grounding/answer) -> citation attestation verification -> SQL route -> global route.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")


def get_json(url: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_sse(url: str, payload: dict, timeout: int = 120) -> list[tuple[str, dict]]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: list[tuple[str, dict]] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = ""
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                etype, data = None, None
                for line in frame.splitlines():
                    if line.startswith("event:"):
                        etype = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                if etype and data:
                    try:
                        events.append((etype, json.loads(data)))
                    except json.JSONDecodeError:
                        events.append((etype, {}))
                if etype == "run_end":
                    return events
    return events


def post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orchestrator", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    base = args.orchestrator.rstrip("/")

    # 1. health
    try:
        health = get_json(f"{base}/api/v1/health")
        check("health", health.get("status") == "ok", f"version={health.get('version')}")
    except Exception as exc:
        check("health", False, str(exc))
        return _summary()

    # 2. stats / corpus
    try:
        stats = get_json(f"{base}/api/v1/stats")
        m = stats["meta"]
        check("corpus seeded", m["documents"] >= 1,
              f"docs={m['documents']}, chunks={m['chunks']}, entities={m['entities']}, "
              f"relations={m['relationships']}, communities={m['communities']}")
    except Exception as exc:
        check("corpus stats", False, str(exc))

    # 3. full SSE agent run
    t0 = time.time()
    question = "How does the Corrective Grader Agent use the CRAG loop and web fallback?"
    ans: dict = {}
    try:
        events = post_sse(f"{base}/api/v1/query", {"query": question, "mode": "auto"})
        kinds = [e for e, _ in events]
        ms = int((time.time() - t0) * 1000)
        check("sse run completes", "run_end" in kinds, f"{len(events)} events in {ms}ms")
        for required in ("run_start", "route_selected", "retrieval_fusion",
                         "rerank_complete", "grade_result", "grounding_check",
                         "answer_delta", "answer"):
            check(f"event:{required}", required in kinds)
        by_type = {e: p for e, p in events}
        route = by_type.get("route_selected", {}).get("payload", {}).get("route")
        check("route selected", bool(route), f"route={route}")
        grade = by_type.get("grade_result", {}).get("payload", {})
        check("grade computed", "confidence" in grade,
              f"confidence={grade.get('confidence')} thr={grade.get('threshold')} "
              f"passed={grade.get('passed')}")
        ans = by_type.get("answer", {}).get("payload", {})
        check("answer non-empty", bool(ans.get("text")), f"{len(ans.get('text', ''))} chars")
        check("citations present", bool(ans.get("citations")),
              f"{len(ans.get('citations', []))} citations")
    except Exception as exc:
        check("sse run", False, str(exc))
        return _summary()

    # 4. citation attestation verification
    cits = ans.get("citations", [])
    if cits:
        c = cits[0]
        try:
            v = post_json(f"{base}/api/v1/verify-citation", {
                "chunk_id": c["chunk_id"], "content_sha256": c["content_sha256"],
                "request_id": c["request_id"], "attestation": c["attestation"],
            })
            check("citation attestation verifies", v.get("valid") is True,
                  f"chunk={c['chunk_id'][:44]}…")
            bad = post_json(f"{base}/api/v1/verify-citation", {
                "chunk_id": c["chunk_id"],
                "content_sha256": "0" * len(c["content_sha256"]),
                "request_id": c["request_id"], "attestation": c["attestation"],
            })
            check("tampered citation rejected", bad.get("valid") is False)
        except Exception as exc:
            check("citation verification", False, str(exc))

    # 5. structured SQL route
    try:
        events = post_sse(f"{base}/api/v1/query",
                          {"query": "how many documents and chunks are in the corpus?"})
        by_type = {e: p for e, p in events}
        kinds = [e for e, _ in events]
        route = by_type.get("route_selected", {}).get("payload", {}).get("route")
        check("sql route dispatched", route == "sql", f"route={route}")
        check("sql_result event", "sql_result" in kinds)
        check("sql answer", bool(by_type.get("answer", {}).get("payload", {}).get("text")))
    except Exception as exc:
        check("sql route run", False, str(exc))

    # 6. global GraphRAG route
    try:
        events = post_sse(f"{base}/api/v1/query",
                          {"query": "overall themes and trends across the platform knowledge mesh",
                           "mode": "global"})
        by_type = {e: p for e, p in events}
        route = by_type.get("route_selected", {}).get("payload", {}).get("route")
        check("global graph route", route == "graph_global", f"route={route}")
        gc = by_type.get("graph_context", {}).get("payload", {})
        check("community context injected", gc.get("mode") == "global",
              f"mode={gc.get('mode')}")
    except Exception as exc:
        check("global route run", False, str(exc))

    return _summary()


def _summary() -> int:
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'-' * 60}\nSMOKE TEST: {passed}/{total} checks passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  x {name} {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

