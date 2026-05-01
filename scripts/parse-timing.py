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
    if any(k in n for k in ["auth", "load metadata", "resolve", "from ", "sha256:", "extracting"]):
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
    phases = {"pull": [], "build": [], "export": [], "other": []}
    for v in vertices.values():
        if not v["started"] or not v["completed"]:
            continue
        phase = classify(v["name"])
        phases[phase].append((parse_time(v["started"]), parse_time(v["completed"])))

    global_start, global_end = None, None
    results = []
    for phase in ["pull", "build", "export"]:
        entries = phases[phase]
        if not entries:
            continue
        earliest = min(s for s, e in entries)
        latest = max(e for s, e in entries)
        dur = (latest - earliest).total_seconds()
        results.append((phase.capitalize(), dur))
        if global_start is None or earliest < global_start:
            global_start = earliest
        if global_end is None or latest > global_end:
            global_end = latest

    for s, e in phases["other"]:
        if global_start is None or s < global_start:
            global_start = s
        if global_end is None or e > global_end:
            global_end = e

    if global_start and global_end:
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
