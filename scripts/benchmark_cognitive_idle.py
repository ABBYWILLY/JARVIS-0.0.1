#!/usr/bin/env python3
"""Compare real idle COMMAND OS processes before/after the Cognitive HUD.

Short software-only samples: main window visible, PRESENCE closed, audio disabled,
no model/server/device opened. RSS is process RAM, never VRAM or model memory.
Each case uses a fresh Python/Tk process and a disposable SQLite archive.
"""
import argparse
import io
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[1]

CHILD = r'''
import hashlib, json, os, sys, tempfile, time, tkinter as tk
from pathlib import Path
from jarvis.storage import Store
from jarvis.ui import App

options=json.loads(sys.argv[1])
source=Path(sys.modules['jarvis.ui'].__file__)
source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()
def rss():
    try:
        return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, AttributeError):
        return None
with tempfile.TemporaryDirectory(prefix='jarvis-idle-sample-') as folder:
    store=Store(Path(folder)/'idle.sqlite3')
    if options['enabled'] is not None:
        store.set_preference('cognitive_hud', {'enabled':options['enabled'],'level':'minimal'})
    root=tk.Tk()
    app=App(root,store,refresh=False)
    observations={'polls':0,'errors':[]}
    previous_poll=app.poll
    def poll():
        observations['polls']+=1
        previous_poll()
    app.poll=poll
    previous_error=root.report_callback_exception
    def report(kind,error,tb):
        observations['errors'].append(kind.__name__)
        previous_error(kind,error,tb)
    root.report_callback_exception=report
    def start():
        observations.update(wall=time.perf_counter(),cpu=time.process_time(),rss_before=rss(),polls_before=observations['polls'])
        root.after(round(options['seconds']*1000),finish)
    def finish():
        elapsed=time.perf_counter()-observations['wall']
        cpu=time.process_time()-observations['cpu']
        result={'wall_seconds':elapsed,'process_cpu_ms':cpu*1000,'process_cpu_percent_one_core':100*cpu/elapsed,
                'rss_before_bytes':observations['rss_before'],'rss_after_bytes':rss(),
                'existing_poll_callbacks':observations['polls']-observations['polls_before'],
                'ui_source_sha256':source_sha256,'callback_errors':observations['errors']}
        app.close()
        print(json.dumps(result))
    root.after(500,start)
    root.mainloop()
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New JSON; never overwritten")
    parser.add_argument("--baseline", default="1985a99")
    parser.add_argument("--seconds", type=float, default=2.)
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args(argv)
    if not 1. <= args.seconds <= 10.:
        parser.error("Measure1–10seconds per case")
    if not 7 <= len(args.baseline) <= 40 or any(char not in "0123456789abcdefABCDEF" for char in args.baseline):
        parser.error("Baseline must be a7–40character commit SHA")
    if args.output.exists():
        parser.error("Output exists; choose a new path")
    cases = {"before": [], "minimal": [], "disabled": []}
    raw = subprocess.check_output(["git", "archive", args.baseline, "jarvis"], cwd=REPO)
    with tempfile.TemporaryDirectory(prefix="jarvis-idle-baseline-") as directory:
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(directory, filter="data")
        for _repeat in range(args.repetitions):
            for name, folder, enabled in (("before", directory, None), ("minimal", REPO, True), ("disabled", REPO, False)):
                result = subprocess.run([sys.executable, "-c", CHILD,
                    json.dumps({"seconds": args.seconds, "enabled": enabled})],
                    cwd=folder, check=True, capture_output=True, text=True)
                observation = json.loads(result.stdout.splitlines()[-1])
                if observation["callback_errors"]:
                    raise RuntimeError("Tk callback error during " + name + ": " + repr(observation["callback_errors"]))
                cases[name].append(observation)
    report = {"scope": __doc__, "platform": platform.platform(), "python": sys.version, "baseline": args.baseline,
              "warmup_seconds": .5, "requested_sample_seconds": args.seconds,
              "repetitions": args.repetitions, "cases": cases,
              "summary": {name: {"median_process_cpu_ms": statistics.median(row["process_cpu_ms"] for row in values),
                                 "median_rss_after_bytes": (statistics.median(row["rss_after_bytes"] for row in values)
                                     if all(row["rss_after_bytes"] is not None for row in values) else None),
                                 "median_existing_poll_callbacks": statistics.median(row["existing_poll_callbacks"] for row in values)}
                          for name, values in cases.items()},
              "limitations": "Short cloud Linux samples; no statistical hardware speedup, TTFT, speech latency, acoustic Bluetooth, power or physical VRAM conclusion. Existing App.poll remains25Hz; only one-shot measurement timers added by this tool."}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
