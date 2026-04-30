#!/usr/bin/env python3
"""Parse buildkit --progress=rawjson output and summarize phase timings.

Reads JSON lines from stdin, groups vertices into phases (pull, build, export),
and prints a markdown summary.
"""
import json
import sys
from datetime import datetime, timezone

def parse_time(s):
    # Handle both "Z" and "+00:00" suffixes, and nanosecond precision
    s = s.replace("Z", "+00:00")
    # Truncate nanoseconds to microseconds for fromisoformat
    if "." in s:
        parts = s.split(".")
        frac, rest = parts[1].split("+") if "+" in parts[1] else (parts[1].split("-")[0], "-" + parts[1].split("-", 1)[1] if "-" in parts[1][1:] else "")
        frac = frac[:6]
        s = parts[0] + "." + frac + "+" + rest.lstrip("+-") if rest else parts[0] + "." + frac + "+00:00"
    return datetime.fromisoformat(s)

def classify(name):
    name_lower = name.lower()
    if "exporting to" in name_lower:
        return "export"
    if any(k in name_lower for k in ["load metadata", "resolve", "from ", "sha256:", "extracting"]):
        return "pull"
    if any(k in name_lower for k in ["run ", "copy ", "workdir", "cmd", "env ", "arg "]):
        return "build"
    if "load build definition" in name_lower or "load .dockerignore" in name_lower:
        return "setup"
    return "other"

def fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"

def main():
    vertices = {}  # digest -> {name, started, completed}

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            status = json.loads(line)
        except json.JSONDecodeError:
            continue

        for v in status.get("vertexes", []):
            digest = v.get("digest", "")
            if digest not in vertices:
                vertices[digest] = {"name": v.get("name", ""), "started": None, "completed": None}
            if v.get("started"):
                vertices[digest]["started"] = v["started"]
            if v.get("completed"):
                vertices[digest]["completed"] = v["completed"]
            if v.get("name"):
                vertices[digest]["name"] = v["name"]

    # Group by phase
    phases = {"pull": [], "build": [], "export": [], "setup": [], "other": []}
    for v in vertices.values():
        if not v["started"] or not v["completed"]:
            continue
        phase = classify(v["name"])
        start = parse_time(v["started"])
        end = parse_time(v["completed"])
        phases[phase].append((start, end, v["name"]))

    # Compute phase durations (wall clock: earliest start to latest end)
    global_start = None
    global_end = None

    results = []
    for phase in ["pull", "build", "export"]:
        entries = phases[phase]
        if not entries:
            continue
        earliest = min(s for s, e, n in entries)
        latest = max(e for s, e, n in entries)
        duration = (latest - earliest).total_seconds()
        results.append((phase.capitalize(), duration))

        if global_start is None or earliest < global_start:
            global_start = earliest
        if global_end is None or latest > global_end:
            global_end = latest

    # Include setup/other in global timing
    for phase in ["setup", "other"]:
        for s, e, n in phases[phase]:
            if global_start is None or s < global_start:
                global_start = s
            if global_end is None or e > global_end:
                global_end = e

    if global_start and global_end:
        total = (global_end - global_start).total_seconds()
        results.append(("Total", total))

    # Output
    for name, duration in results:
        print(f"| {name} | {fmt_duration(duration)} |")

if __name__ == "__main__":
    main()
