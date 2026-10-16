#!/usr/bin/env python3
"""Record each hosted version's date and size in history.json.

history.json: { slug: { version: { "seen": ISO time first recorded, "date": release or snapshot date, "bytes": hosted size } } }
Existing entries are kept, so the file grows into a record of how each app changes over time.
"""
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone

SITE = "https://vibeclones.github.io"
ORG = "vibeclones"


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout and r.stdout.strip() else None


def versions_of(slug):
    try:
        with urllib.request.urlopen(f"{SITE}/{slug}/versions.json", timeout=20) as r:
            return json.load(r).get("versions", [])
    except Exception:
        return None


catalog = json.load(open("catalog.json", encoding="utf-8"))
history = json.load(open("history.json", encoding="utf-8")) if os.path.exists("history.json") else {}
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

for app in catalog["apps"]:
    slug = app["slug"]
    versions = versions_of(slug)
    if not versions:
        continue
    known = history.setdefault(slug, {})
    todo = [v for v in versions if not known.get(v, {}).get("bytes")]
    if not todo:
        continue

    tree = gh(f"repos/{ORG}/{slug}/git/trees/main?recursive=1")
    blobs = tree["tree"] if tree else []
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:/|$)", app.get("source", ""))
    upstream = m.group(1) if m else None

    for v in todo:
        entry = known.setdefault(v, {"seen": now})
        entry["bytes"] = sum(b.get("size", 0) for b in blobs if b["path"].startswith(f"v{v}/"))
        snap = re.match(r"(\d{4})\.(\d{2})\.(\d{2})-", v)
        if snap:
            entry["date"] = f"{snap[1]}-{snap[2]}-{snap[3]}"
        elif upstream and "date" not in entry:
            rel = gh(f"repos/{upstream}/releases/tags/v{v}")
            if rel and rel.get("published_at"):
                entry["date"] = rel["published_at"]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, indent=1, sort_keys=True)
    f.write("\n")
print(sum(len(v) for v in history.values()), "versions recorded across", len(history), "apps")
