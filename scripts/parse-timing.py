#!/usr/bin/env python3
"""Filter buildkit --progress=rawjson into readable live output.

Pipe mode (default): reads JSON lines from stdin, prints vertex status
as it happens, and writes a timing summary at the end.

Summary mode (--summary FILE): reads a saved jsonl file and outputs
a markdown timing table to stdout.
"""
import json
import sys
from datetime import datetime


def parse_time(s):
    s = s.replace("Z", "+00:00")
    if "." in s:
        dot = s.index(".")
        plus = s.find("+", dot)
        if plus == -1:
            plus = s.find("-", dot + 1)
        if plus == -1:
            s = s[:dot + 7] + "+00:00"
        else:
            s = s[:dot + 7] + s[plus:]
    return datetime.fromisoformat(s)


def fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def classify(name):
    n = name.lower()
    if "exporting to" in n:
        return "export"
    if any(k in n for k in ["load metadata", "resolve", "from ", "sha256:", "extracting"]):
        return "pull"
    if any(k in n for k in ["run ", "copy ", "workdir"]):
        return "build"
    return "other"


def process_events(lines, live=False):
    vertices = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            status = json.loads(line)
        except json.JSONDecodeError:
            continue
        for v in status.get("vertexes", []):
            d = v.get("digest", "")
            if d not in vertices:
                vertices[d] = {"name": "", "started": None, "completed": None, "cached": False}
            if v.get("name"):
                vertices[d]["name"] = v["name"]
            if v.get("cached"):
                vertices[d]["cached"] = True
            if v.get("started") and not vertices[d]["started"]:
                vertices[d]["started"] = v["started"]
                if live:
                    name = vertices[d]["name"]
                    if name and not name.startswith("[internal]"):
                        print(f"  > {name}", file=sys.stderr, flush=True)
            if v.get("completed"):
                vertices[d]["completed"] = v["completed"]
                if live:
                    name = vertices[d]["name"]
                    started = parse_time(vertices[d]["started"])
                    completed = parse_time(v["completed"])
                    dur = (completed - started).total_seconds()
                    cached = " (cached)" if vertices[d]["cached"] else ""
                    if name and not name.startswith("[internal]"):
                        print(f"  < {name} [{fmt_duration(dur)}{cached}]", file=sys.stderr, flush=True)
        if live:
            for log in status.get("logs", []):
                data = log.get("data")
                if data:
                    try:
                        import base64
                        text = base64.b64decode(data).decode("utf-8", errors="replace")
                    except Exception:
                        text = str(data)
                    for line_text in text.splitlines():
                        print(f"    {line_text}", file=sys.stderr, flush=True)
    return vertices


def summary(vertices):
    # Collect all vertex timestamps.
    all_times = []
    pull_ends = []
    export_starts = []

    for v in vertices.values():
        if not v["started"] or not v["completed"]:
            continue
        s = parse_time(v["started"])
        e = parse_time(v["completed"])
        all_times.append((s, e))
        phase = classify(v["name"])
        if phase == "pull":
            pull_ends.append(e)
        if phase == "export":
            export_starts.append(s)

    if not all_times:
        return []

    global_start = min(s for s, e in all_times)
    global_end = max(e for s, e in all_times)

    results = []

    # Pull: from time 0 (global start) to the last pull vertex completing.
    if pull_ends:
        pull_end = max(pull_ends)
        results.append(("Pull", (pull_end - global_start).total_seconds()))
    else:
        pull_end = global_start

    # Export: from the first "exporting to" vertex starting to the end.
    if export_starts:
        export_start = min(export_starts)
        results.append(("Build", (export_start - pull_end).total_seconds()))
        results.append(("Export", (global_end - export_start).total_seconds()))
    else:
        results.append(("Build", (global_end - pull_end).total_seconds()))

    results.append(("Total", (global_end - global_start).total_seconds()))

    return results


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        with open(sys.argv[2]) as f:
            vertices = process_events(f, live=False)
        for name, dur in summary(vertices):
            print(f"| {name} | {fmt_duration(dur)} |")
    else:
        vertices = process_events(sys.stdin, live=True)
        print("", file=sys.stderr)
        for name, dur in summary(vertices):
            print(f"  {name}: {fmt_duration(dur)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
