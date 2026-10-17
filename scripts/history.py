#!/usr/bin/env python3
"""Record each app's versions, with dates (and sizes where we host a copy), in history.json.

history.json: { slug: { version: { "seen": ISO time first recorded, "date": release or snapshot date,
                                    "bytes": hosted size, "tracked": true if only noted from upstream } } }
Existing entries are kept, so the file grows into a record of how each app changes over time.

Two sources:
  * Apps we host a copy of: the versions in /<slug>/versions.json, with the hosted size.
  * Apps we don't host (the author's own site is the official copy): versions are noted straight from the
    author's GitHub repo, with no copy kept. A repo that publishes releases is read as releases; one that
    doesn't is read as dated snapshots of its latest commit (to a path inside the repo if the catalog gives
    `trackPath`, otherwise of the repo as a whole).
Set FORCE_TRACK=slug1,slug2 to treat those apps as unhosted even while a mirror still exists (for testing).
"""
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone

SITE = "https://vibeclones.github.io"
ORG = "vibeclones"
FORCE_TRACK = {s for s in os.environ.get("FORCE_TRACK", "").split(",") if s}
MAX_RELEASES = 15


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout and r.stdout.strip() else None


def versions_of(slug):
    if slug in FORCE_TRACK:
        return None
    try:
        with urllib.request.urlopen(f"{SITE}/{slug}/versions.json", timeout=20) as r:
            return json.load(r).get("versions", [])
    except Exception:
        return None


def repo_and_path(app):
    """owner/repo and an optional path inside it, from the catalog's source link."""
    m = re.match(r"https://github\.com/([^/]+/[^/#?]+)(?:/tree/[^/]+/(.+))?", app.get("source", ""))
    if not m:
        return None, None
    return m.group(1), app.get("trackPath") or m.group(2)


def track_upstream(app, known):
    """Note an unhosted app's versions from its own repo. Returns how many new entries were added."""
    repo, path = repo_and_path(app)
    if not repo:
        return 0
    added = 0
    rels = gh(f"repos/{repo}/releases?per_page={MAX_RELEASES}") or []
    stable = [r for r in rels if not r.get("draft") and not r.get("prerelease")
              and re.match(r"v?\d", r.get("tag_name", "")) and "nightly" not in r["tag_name"]]
    # An app that names a folder to follow (trackPath) is read as dated snapshots of that folder, even if the repo
    # also publishes releases (for example desktop installers that don't match the web app).
    if stable and not app.get("trackPath"):
        for r in stable:
            v = r["tag_name"].lstrip("v")
            if v not in known:
                known[v] = {"seen": now, "date": r.get("published_at") or "", "tracked": True}
                added += 1
            elif not known[v].get("date") and r.get("published_at"):
                known[v]["date"] = r["published_at"]  # fill in a date an earlier run couldn't find
        return added
    # No numbered releases: a dated snapshot of the latest commit (touching the path, if there is one).
    q = f"repos/{repo}/commits?per_page=1" + (f"&path={path}" if path else "")
    commits = gh(q) or []
    if commits:
        c = commits[0]
        d = c["commit"]["committer"]["date"][:10]
        v = f"{d.replace('-', '.')}-{c['sha'][:7]}"
        if v not in known:
            known[v] = {"seen": now, "date": d, "tracked": True}
            added += 1
    return added


catalog = json.load(open("catalog.json", encoding="utf-8"))
history = json.load(open("history.json", encoding="utf-8")) if os.path.exists("history.json") else {}
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
tracked_added = 0

for app in catalog["apps"]:
    slug = app["slug"]
    versions = versions_of(slug)
    if not versions:
        # Not hosted by us: if the author hosts it, keep noting its versions from their repo.
        # (A desktop-only app has no web app to host, so it is always noted this way.)
        if app.get("official") or app.get("platform") == "desktop":
            tracked_added += track_upstream(app, history.setdefault(slug, {}))
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
        entry.pop("tracked", None)
        entry["bytes"] = sum(b.get("size", 0) for b in blobs if b["path"].startswith(f"v{v}/"))
        snap = re.match(r"(\d{4})\.(\d{2})\.(\d{2})-", v)
        if snap:
            entry["date"] = f"{snap[1]}-{snap[2]}-{snap[3]}"
        elif upstream and "date" not in entry:
            # Tags are usually v1.2.3, but some projects tag 1.2.3 with no "v".
            rel = gh(f"repos/{upstream}/releases/tags/v{v}") or gh(f"repos/{upstream}/releases/tags/{v}")
            if rel and rel.get("published_at"):
                entry["date"] = rel["published_at"]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, indent=1, sort_keys=True)
    f.write("\n")
print(sum(len(v) for v in history.values()), "versions recorded across", len(history), "apps;", tracked_added, "new from upstream")
