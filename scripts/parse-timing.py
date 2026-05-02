#!/usr/bin/env python3
"""Filter buildkit --progress=rawjson into readable live output.

Pipe mode (default): reads JSON lines from stdin, prints vertex status
as it happens, and writes a timing summary at the end.

Summary mode (--summary FILE): reads a saved jsonl file and outputs
a markdown timing table to stdout.
"""
import base64
import json
import sys
from datetime import datetime


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
                    s = datetime.fromisoformat(vertices[d]["started"])
                    e = datetime.fromisoformat(v["completed"])
                    cached = " (cached)" if vertices[d]["cached"] else ""
                    if name and not name.startswith("[internal]"):
                        print(f"  < {name} [{str(e - s)}{cached}]", file=sys.stderr, flush=True)
        if live:
            for log in status.get("logs", []):
                data = log.get("data")
                if data:
                    try:
                        text = base64.b64decode(data).decode("utf-8", errors="replace")
                    except Exception:
                        text = str(data)
                    for line_text in text.splitlines():
                        print(f"    {line_text}", file=sys.stderr, flush=True)
    return vertices


def summary(vertices):
    all_times = []
    pull_ends = []
    export_starts = []

    for v in vertices.values():
        if not v["started"] or not v["completed"]:
            continue
        s = datetime.fromisoformat(v["started"])
        e = datetime.fromisoformat(v["completed"])
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

    if pull_ends:
        pull_end = max(pull_ends)
        results.append(("Pull", pull_end - global_start))
    else:
        pull_end = global_start

    if export_starts:
        export_start = min(export_starts)
        results.append(("Build", export_start - pull_end))
        results.append(("Export", global_end - export_start))
    else:
        results.append(("Build", global_end - pull_end))

    results.append(("Total", global_end - global_start))

    return results


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        with open(sys.argv[2]) as f:
            vertices = process_events(f, live=False)
        for name, dur in summary(vertices):
            print(f"| {name} | {str(dur)} |")
    else:
        vertices = process_events(sys.stdin, live=True)
        print("", file=sys.stderr)
        for name, dur in summary(vertices):
            print(f"  {name}: {str(dur)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
