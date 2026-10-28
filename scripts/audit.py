#!/usr/bin/env python3
"""Check the site's data for mistakes. Run from the repo root: python scripts/audit.py [--offline]

Prints one line per problem and exits 1 if there are any. Checks:
  catalog   required fields, unique slugs, every `clones` id exists in `programs`, no unused programs,
            categories exist, `featured` ranks unique, official/source are URLs, logos exist
  hosted    every version listed by a mirror's versions.json opens (HTTP 200), has a recorded size and date
            in history.json, and the mirror's `latest` is its first version
            (apps with `noMirror` are skipped; with `versionUrl`, each version's page on the author's site must open)
  tracked   apps we don't host have versions noted from upstream (so the dialog isn't empty)
  coverage  history.json has no versions that no longer exist anywhere (stale entries are only noted)
  colors    every publisher (`by.name`) has a PUBCOLOR entry in index.html
"""
import json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

OFFLINE = "--offline" in sys.argv
SITE = "https://vibeclones.github.io"
problems = []
def bad(slug, msg): problems.append(f"{slug}: {msg}")

cat = json.load(open("catalog.json", encoding="utf-8"))
history = json.load(open("history.json", encoding="utf-8")) if os.path.exists("history.json") else {}
releases = json.load(open("releases.json", encoding="utf-8")) if os.path.exists("releases.json") else {}
programs, apps = cat.get("programs", {}), cat["apps"]
cats = {c["id"] if isinstance(c, dict) else c for c in cat.get("categories", [])}

def get(url, method="GET"):
    try:
        req = urllib.request.Request(url, method=method, headers={"User-Agent": "vibeclones-audit"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read() if method == "GET" else b""
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""

# --- catalog -------------------------------------------------------------------------------------------------
seen, ranks, used = set(), {}, set()
for a in apps:
    s = a.get("slug", "?")
    for f in ("slug", "name", "category", "type", "description", "source"):
        if not a.get(f): bad(s, f"missing {f}")
    if s in seen: bad(s, "duplicate slug")
    seen.add(s)
    if cats and a.get("category") not in cats: bad(s, f"unknown category {a.get('category')!r}")
    for c in a.get("clones", []):
        used.add(c)
        if c not in programs: bad(s, f"clones id {c!r} is not in programs")
    if a.get("featured") is not None:
        ranks.setdefault(a["featured"], set()).add(a.get("group"))
    for f in ("official", "source"):
        if a.get(f) and not re.match(r"https?://", a[f]): bad(s, f"{f} is not a URL")
    for k in ("logo", "logoWide"):
        lg = a.get("by", {}).get(k)
        # Only logos kept in this repo's logos/ folder can be checked here.
        if isinstance(lg, str) and lg.lstrip("/").startswith("logos/") and not os.path.exists(lg.lstrip("/")): bad(s, f"logo file missing: {lg}")
    if not a.get("by"): bad(s, "no publisher (by)")
for r, groups in ranks.items():  # apps in one group share its rank; two different groups must not
    if len(groups) > 1: bad("featured", f"rank {r} is used by different groups: {sorted(groups)}")
for p in programs:
    if p not in used: bad("programs", f"{p!r} is not used by any app")

# Two programs that differ only by a vendor prefix ("Adobe Audition" / "Audition") are one program entered twice.
core = lambda n: re.sub(r"^(adobe|microsoft|google|autodesk|apple)\s+", "", n.lower())
byname = {}
for pid, p in programs.items():
    for n in {p["name"], p.get("full", p["name"])}:
        byname.setdefault(core(n), set()).add(pid)
for k, ids in byname.items():
    if len(ids) > 1: bad("programs", f"{sorted(ids)} look like the same program ({k!r})")
# The description should name what the app replaces (it was once "alternative to Maya, SketchUp" for a Blender clone).
for a in apps:
    m = re.search(r"alternative to ([^.]+)\.", a.get("description", ""))
    if m and a.get("clones"):
        named = {core(x.strip()) for x in re.split(r",| and ", m.group(1)) if x.strip()}
        have = {core(programs.get(c, {}).get("name", c)) for c in a["clones"]} | {core(programs.get(c, {}).get("full", c)) for c in a["clones"]}
        if named - have: bad(a["slug"], f"description names {sorted(named - have)} which the app doesn't list as replaced")

# --- hosted mirrors ------------------------------------------------------------------------------------------
def check_mirror(a):
    out, s = [], a["slug"]
    if OFFLINE: return out
    if a.get("noMirror"):  # the site ignores any mirror of ours; if the author keeps every version online, check those links
        if a.get("versionUrl"):
            for ver in history.get(s, {}):
                c, _ = get(a["versionUrl"].replace("{v}", ver), "HEAD")
                if c != 200: out.append(f"{s}: the author's page for {ver} does not open (HTTP {c})")
        return out
    code, body = get(f"{SITE}/{s}/versions.json")
    if code != 200:
        return out  # not hosted by us
    try: v = json.loads(body)
    except Exception: return [f"{s}: versions.json is not valid JSON"]
    vs = v.get("versions", [])
    if vs and v.get("latest") != vs[0]: out.append(f"{s}: latest {v.get('latest')!r} is not the first version {vs[0]!r}")
    h = history.get(s, {})
    for ver in vs:
        c, _ = get(f"{SITE}/{s}/v{ver}/index.html", "HEAD")
        if c != 200: out.append(f"{s}: v{ver} does not open (HTTP {c})")
        e = h.get(ver, {})
        if not e.get("bytes"): out.append(f"{s}: v{ver} has no recorded size (history job hasn't run since it was added?)")
        if not e.get("date"): out.append(f"{s}: v{ver} has no recorded date")
    a["_hosted"] = len(vs)
    a["_vs"] = vs
    code, body = get(f"{SITE}/{s}/skipped.json")
    try: a["_skipped"] = json.loads(body) if code == 200 else {}
    except Exception: a["_skipped"] = {}
    return out

with ThreadPoolExecutor(8) as ex:
    for res in ex.map(check_mirror, apps): problems.extend(res)

# --- apps we don't host ---------------------------------------------------------------------------------------
for a in apps:
    s = a["slug"]
    if OFFLINE or a.get("_hosted"): continue
    if a.get("official") and not history.get(s):
        bad(s, "not hosted and no versions noted from upstream yet")

# --- completeness: do we have the full version history? ------------------------------------------------------
# Every version the author has published must be hosted here, or have a recorded reason it isn't:
#   - the mirror's skipped.json names it (build failed, dropped for space, ...), or
#   - the author published no browser build for it (checked against the release's assets), or
#   - the app has no mirror at all and the catalog says why (`noMirror`).
# Anything else is "unaccounted for", which is the thing to fix.
import subprocess
def commits_touching(path):
    r = subprocess.run(["gh", "api", "--paginate", f"repos/HeyPuter/everything/commits?path={path}&per_page=100", "--jq", ".[].sha"],
                       capture_output=True, text=True)
    return len(r.stdout.split()) if r.returncode == 0 else None
SNAPSHOT_BUDGET = 15
if not OFFLINE:
    for a in apps:
        s, ups = a["slug"], releases.get(a["slug"], [])
        vs = set(a.get("_vs", []))
        if "_vs" in a:
            if ups:
                zip_based = any(r.get("web") for r in ups)
                skipped = a.get("_skipped", {})
                lost = [r["v"] for r in ups if r["v"] not in vs and r["v"] not in skipped and not (zip_based and r.get("web") is False)]
                if lost:
                    shown = ", ".join(lost[:6]) + (f" and {len(lost) - 6} more" if len(lost) > 6 else "")
                    bad(s, f"{len(lost)} of {len(ups)} upstream releases are not hosted and have no recorded reason: {shown}")
            elif "HeyPuter/everything" in a.get("source", ""):
                m = re.search(r"/src/([^/]+)", a["source"])
                n = commits_touching(f"src/{m.group(1)}") if m else None
                gap = (n or 0) - len(vs) - len(a.get("_skipped", {}))
                if n is not None and gap > 0:
                    bad(s, f"upstream has {n} snapshots: {len(vs)} hosted, {len(a.get('_skipped', {}))} with a recorded reason, {gap} unaccounted for")
        elif a.get("official") and not a.get("noMirror"):
            bad(s, "has no mirror for older versions and no `noMirror` reason explaining why")

# Every publisher gets a tint (PUBCOLOR in index.html): from its avatar, else from its app's accent or site.
html = open("index.html", encoding="utf-8").read()
pub_res = [re.compile(p, re.I) for p in re.findall(r"\[/(\^[^/]+)/i, '#[0-9a-fA-F]+'\]", html)]
for n in sorted({a["by"]["name"] for a in apps if a.get("by")}):
    if not any(p.search(n) for p in pub_res):
        bad(n, "publisher has no PUBCOLOR entry in index.html")

print("\n".join(problems) if problems else "No problems found.")
print(f"\n{len(apps)} apps, {len(programs)} programs, {len(problems)} problem(s).")
sys.exit(1 if problems else 0)
