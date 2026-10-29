#!/usr/bin/env python3
"""Compare historical/current context reads on disposable synthetic SQLite data.

No user database, model, microphone or network is opened. The historical method
is structurally checked against the chosen local Git revision; timings alternate
on the same warmed database. Tracemalloc records Python allocations, not total
process RSS or VRAM. This does not benchmark the entire C1 context builder.
"""
import argparse
import ast
import hashlib
import inspect
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time
import tracemalloc

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from jarvis.storage import Store


def baseline_context_records(self, sid):
    rows = self.messages(sid)
    result = []
    for i in range(0, len(rows) - 1, 2):
        user, assistant = rows[i:i + 2]
        if user["role"] == "user" and assistant["role"] == "assistant" and assistant["status"] == "complete":
            result.extend({key: row[key] for key in ("id", "session_id", "role", "content", "created")}
                          for row in (user, assistant))
    return result


def check_baseline(revision):
    source = subprocess.check_output(["git", "show", revision + ":jarvis/storage.py"], cwd=REPO, text=True)
    tree = ast.parse(source)
    method = next(item for owner in tree.body if isinstance(owner, ast.ClassDef) and owner.name == "Store"
                  for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == "context_records")
    reference = ast.parse(textwrap.dedent(inspect.getsource(baseline_context_records))).body[0]
    method.name = reference.name
    if ast.dump(method) != ast.dump(reference):
        raise ValueError("The selected baseline method differs from the preserved historical algorithm.")
    commit = subprocess.check_output(["git", "rev-parse", revision + "^{commit}"], cwd=REPO, text=True).strip()
    return commit, hashlib.sha256(source.encode()).hexdigest()


def run_benchmark(*, turns=400, repetitions=20, baseline="19c003a"):
    commit, original_sha = check_baseline(baseline)
    content = ("Texte de benchmark synthétique. " * 67)[:2048]
    metadata = json.dumps({"context": {"system_instructions": "X" * 8192,
                                     "sources": [{"excerpt": "Y" * 240}] * 5}})
    with tempfile.TemporaryDirectory(prefix="jarvis-context-benchmark-") as directory:
        store = Store(Path(directory) / "synthetic.sqlite3")
        try:
            sid = store.new_session()
            with store.db:
                store.db.executemany(
                    "INSERT INTO messages(session_id,role,content,status,metadata) VALUES (?,?,?,?,?)",
                    [(sid, role, content, "complete", metadata)
                     for _ in range(turns) for role in ("user", "assistant")])
            cases = {"before": lambda: baseline_context_records(store, sid),
                     "after": lambda: store.context_records(sid)}
            expected = cases["before"]()
            assert expected == cases["after"](), "Context semantics changed"
            samples = {key: [] for key in cases}
            for _ in range(3):
                for function in cases.values():
                    function()
            for repetition in range(repetitions):
                # Alternate order to reduce cache/order bias.
                for key in tuple(cases)[::1 if repetition % 2 == 0 else -1]:
                    started = time.perf_counter()
                    result = cases[key]()
                    elapsed = (time.perf_counter() - started) * 1000
                    assert result == expected, "Context output changed during repeated reads"
                    samples[key].append(elapsed)
                    del result
            measurements = {}
            for key, function in cases.items():
                tracemalloc.start()
                result = function()
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                assert result == expected
                measurements[key] = {"samples_ms": samples[key],
                                     "median_ms": statistics.median(samples[key]),
                                     "max_ms": max(samples[key]),
                                     "tracemalloc_peak_bytes": peak,
                                     "returned_records": len(result)}
                del result
            query_plan = [list(row) for row in store.db.execute(
                "EXPLAIN QUERY PLAN SELECT id,session_id,role,content,created,status "
                "FROM messages WHERE session_id=? ORDER BY id", (sid,))]
            integrity = store.db.execute("PRAGMA integrity_check").fetchone()[0]
            import sqlite3
            report = {"scope": __doc__, "platform": platform.platform(), "python": sys.version,
                      "sqlite_version": sqlite3.sqlite_version,
                      "baseline_commit": commit, "baseline_storage_sha256": original_sha,
                      "current_storage_sha256": hashlib.sha256((REPO / "jarvis/storage.py").read_bytes()).hexdigest(),
                      "conditions": {"synthetic": True, "turns": turns, "messages": turns * 2,
                                     "content_chars_per_message": len(content),
                                     "metadata_bytes_per_message": len(metadata.encode()),
                                     "cache": "warm SQLite/OS; 3 warmup reads per case",
                                     "repetitions": repetitions},
                      "query_plan": query_plan, "equal_results": True,
                      "integrity_check": integrity, "measurements": measurements}
        finally:
            store.close()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New JSON file; never overwrite")
    parser.add_argument("--baseline", default="19c003a", help="Local Git commit containing the historical method")
    parser.add_argument("--turns", type=int, default=400)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args(argv)
    if not 1 <= args.turns <= 5000 or not 3 <= args.repetitions <= 100:
        parser.error("Use 1–5000 turns and 3–100 repetitions")
    if (not 7 <= len(args.baseline) <= 40
            or any(character not in "0123456789abcdefABCDEF" for character in args.baseline)):
        parser.error("Baseline must be a 7–40-character commit SHA")
    if args.output.exists():
        parser.error("Output exists; choose a new path")
    report = run_benchmark(turns=args.turns, repetitions=args.repetitions, baseline=args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    for key, values in report["measurements"].items():
        print(f"{key}: {values['median_ms']:.3f} ms median; "
              f"{values['tracemalloc_peak_bytes']} Python allocation peak bytes")
    print("Exact context equality and SQLite integrity:", report["equal_results"], report["integrity_check"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
