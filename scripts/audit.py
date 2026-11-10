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

Two kinds of finding are printed apart from the problems, under "Not counted as problems", and never fail the run:
  couldn't check   a request that gets no answer (or a 429/5xx) is retried for up to ~45 s (GitHub Pages can answer 503
                   that long before the 404 for a missing file), then reported as unchecked instead of as a broken page.
                   (If vibeclones.github.io itself answers nothing, that is a problem: nothing was checked.)
  pending          the mirrors look at upstream on a schedule, so a release or snapshot younger than GRACE_H hasn't had
                   its turn yet, and a version hosted since the history job last ran isn't in history.json yet.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

OFFLINE = "--offline" in sys.argv
SITE = "https://vibeclones.github.io"
SITE_HOST = urllib.parse.urlsplit(SITE).netloc
# Scheduled workflows run less often than their cron lines say: in practice the release mirrors run every 4-16 hours,
# the Puter apps' nightly build once a day (some hours late), and the history job every 4-13 hours.
GRACE_H = 36   # how long a new release or snapshot may stay unhosted before it counts as missing
RECORD_H = 12  # on top of that, how long a hosted version may stay out of history.json
# GitHub Pages has been seen answering 503 for up to ~45 s before it admits that a file doesn't exist (a mirror with no
# skipped.json), so a request that gets no usable answer is tried up to TRIES times, PAUSE_S seconds apart, unless it has
# already been at it for GIVE_UP_S (a host that hangs for the whole 25 s of each try would otherwise keep us waiting for
# minutes).
TRIES, PAUSE_S, GIVE_UP_S = 4, 15, 40
NOW = datetime.now(timezone.utc)
problems, notes = [], []
def bad(slug, msg): problems.append(f"{slug}: {msg}")
def note(slug, msg): notes.append(f"{slug}: {msg}")

cat = json.load(open("catalog.json", encoding="utf-8"))
history = json.load(open("history.json", encoding="utf-8")) if os.path.exists("history.json") else {}
releases = json.load(open("releases.json", encoding="utf-8")) if os.path.exists("releases.json") else {}
programs, apps = cat.get("programs", {}), cat["apps"]
cats = {c["id"] if isinstance(c, dict) else c for c in cat.get("categories", [])}

net = []  # (host, status) of every request once its tries are used up, to notice if a whole host went quiet
def unanswered(code):
    """No answer at all, or the server asked us to come back later: that says nothing about the page itself."""
    return code == 0 or code == 429 or code >= 500
def answer(code): return "no answer" if code == 0 else f"HTTP {code}"

def get(url, method="GET", tries=TRIES):
    t0 = time.monotonic()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "vibeclones-audit"})
            with urllib.request.urlopen(req, timeout=25) as r:
                code, body = r.status, r.read() if method == "GET" else b""
        except urllib.error.HTTPError as e:
            code, body = e.code, b""
        except Exception:
            code, body = 0, b""  # 0 = no answer (timeout, reset, DNS, ...)
        if not unanswered(code) or attempt == tries - 1 or time.monotonic() - t0 > GIVE_UP_S: break
        time.sleep(PAUSE_S)
    net.append((urllib.parse.urlsplit(url).netloc, code))
    return code, body

def age_h(stamp):
    """Hours since an ISO timestamp, or since the end of a bare YYYY-MM-DD date; None if there is no usable date."""
    try:
        if len(stamp) == 10: t = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc) + timedelta(days=1)
        else: t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return (NOW - t).total_seconds() / 3600
    except Exception:
        return None
def younger(stamp, hours):
    age = age_h(stamp or "")
    return age is not None and age < hours
def is_new(slug, ver):
    """Did this version come out so recently that a mirror, then the history job, may not have caught up with it yet?"""
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})-", ver)  # a dated snapshot, e.g. 2026.11.10-8babd9c
    published = f"{m[1]}-{m[2]}-{m[3]}" if m else next((r.get("date") for r in releases.get(slug, []) if r["v"] == ver), "")
    return younger(published, GRACE_H + RECORD_H)

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
    out, nts, s = [], [], a["slug"]  # problems, and things we couldn't check or that are still pending
    if OFFLINE: return out, nts
    if a.get("noMirror"):  # the site ignores any mirror of ours; if the author keeps every version online, check those links
        if a.get("versionUrl"):
            for ver in history.get(s, {}):
                url = a["versionUrl"].replace("{v}", ver)
                c, _ = get(url, "HEAD")
                if unanswered(c):  # the author's site is down or slow; the rest of its pages would only time out too
                    nts.append(f"{s}: couldn't check the author's pages from {ver} on ({answer(c)} from {urllib.parse.urlsplit(url).netloc})")
                    break
                if c != 200: out.append(f"{s}: the author's page for {ver} does not open (HTTP {c})")
        return out, nts
    code, body = get(f"{SITE}/{s}/versions.json")
    if unanswered(code):
        a["_unchecked"] = True
        nts.append(f"{s}: couldn't read versions.json ({answer(code)}), so its mirror wasn't checked")
        return out, nts
    if code != 200:
        return out, nts  # not hosted by us
    try: v = json.loads(body)
    except Exception: return [f"{s}: versions.json is not valid JSON"], nts
    vs = v.get("versions", [])
    if vs and v.get("latest") != vs[0]: out.append(f"{s}: latest {v.get('latest')!r} is not the first version {vs[0]!r}")
    h = history.get(s, {})
    opens, waiting = True, []
    for ver in vs:
        if opens:
            c, _ = get(f"{SITE}/{s}/v{ver}/index.html", "HEAD")
            if unanswered(c):
                opens = False  # the rest would only fail the same way
                nts.append(f"{s}: couldn't check that its versions open, from v{ver} on ({answer(c)})")
            elif c != 200:
                out.append(f"{s}: v{ver} does not open (HTTP {c})")
        e = h.get(ver, {})
        if (not e.get("bytes") or not e.get("date")) and is_new(s, ver):
            waiting.append(ver)  # hosted since the history job last ran
            continue
        if not e.get("bytes"): out.append(f"{s}: v{ver} has no recorded size (history job hasn't run since it was added?)")
        if not e.get("date"): out.append(f"{s}: v{ver} has no recorded date")
    if waiting:
        nts.append(f"{s}: {', '.join('v' + w for w in waiting)} not in history.json yet (the next history run records {'it' if len(waiting) == 1 else 'them'})")
    a["_hosted"] = len(vs)
    a["_vs"] = vs
    code, body = get(f"{SITE}/{s}/skipped.json")
    if unanswered(code):
        a["_skipped"] = None  # unknown: the completeness check below leaves this app out
        nts.append(f"{s}: couldn't read skipped.json ({answer(code)}), so what's missing from it wasn't checked")
    else:
        try: a["_skipped"] = json.loads(body) if code == 200 else {}
        except Exception: a["_skipped"] = {}
    return out, nts

with ThreadPoolExecutor(8) as ex:
    for res, nts in ex.map(check_mirror, apps):
        problems.extend(res)
        notes.extend(nts)

# --- apps we don't host ---------------------------------------------------------------------------------------
for a in apps:
    s = a["slug"]
    if OFFLINE or a.get("_hosted") or a.get("_unchecked"): continue
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
    """Every upstream commit that touches a path, newest first, as (version tag, commit time): the tag is how the
    mirrors name a snapshot (the commit's date and the first 7 characters of its id). None if gh failed."""
    r = subprocess.run(["gh", "api", "--paginate", f"repos/HeyPuter/everything/commits?path={path}&per_page=100", "--jq",
                        ".[] | [.sha, .commit.committer.date] | @tsv"], capture_output=True, text=True)
    if r.returncode != 0: return None
    rows = [line.split("\t") for line in r.stdout.splitlines() if "\t" in line]
    return [(f"{date[:10].replace('-', '.')}-{sha[:7]}", date) for sha, date in rows]
SNAPSHOT_BUDGET = 15
if not OFFLINE:
    for a in apps:
        s, ups = a["slug"], releases.get(a["slug"], [])
        vs = set(a.get("_vs", []))
        if a.get("_unchecked"): continue  # its mirror couldn't be read (noted above)
        if "_vs" in a:
            skipped = a.get("_skipped")
            if skipped is None: continue  # skipped.json couldn't be read (noted above)
            if ups:
                zip_based = any(r.get("web") for r in ups)
                missing = [r for r in ups if r["v"] not in vs and r["v"] not in skipped and not (zip_based and r.get("web") is False)]
                lost = [r["v"] for r in missing if not younger(r.get("date"), GRACE_H)]
                new = [r["v"] for r in missing if younger(r.get("date"), GRACE_H)]
                if lost:
                    shown = ", ".join(lost[:6]) + (f" and {len(lost) - 6} more" if len(lost) > 6 else "")
                    bad(s, f"{len(lost)} of {len(ups)} upstream releases are not hosted and have no recorded reason: {shown}")
                if new:
                    note(s, f"{', '.join(new)} came out less than {GRACE_H} hours ago; the mirror hasn't had its turn yet")
            elif "HeyPuter/everything" in a.get("source", ""):
                m = re.search(r"/src/([^/]+)", a["source"])
                commits = commits_touching(f"src/{m.group(1)}") if m else []
                if commits is None:
                    note(s, "couldn't list the upstream commits (gh api failed), so its snapshots weren't counted")
                    continue
                unaccounted = [date for tag, date in commits if tag not in vs and tag not in skipped]
                gap = sum(1 for date in unaccounted if not younger(date, GRACE_H))
                if gap:
                    bad(s, f"upstream has {len(commits)} snapshots: {len(vs)} hosted, {len(skipped)} with a recorded reason, {gap} unaccounted for")
                if len(unaccounted) > gap:
                    note(s, f"{len(unaccounted) - gap} upstream snapshot(s) came out less than {GRACE_H} hours ago; the nightly build hasn't had its turn yet")
        elif a.get("official") and not a.get("noMirror"):
            bad(s, "has no mirror for older versions and no `noMirror` reason explaining why")

# Every publisher gets a tint (PUBCOLOR in index.html): from its avatar, else from its app's accent or site.
html = open("index.html", encoding="utf-8").read()
pub_res = [re.compile(p, re.I) for p in re.findall(r"\[/(\^[^/]+)/i, '#[0-9a-fA-F]+'\]", html)]
for n in sorted({a["by"]["name"] for a in apps if a.get("by")}):
    if not any(p.search(n) for p in pub_res):
        bad(n, "publisher has no PUBCOLOR entry in index.html")

# If our own site answered nothing at all, every mirror check above ended as "couldn't check": that is a problem too.
site = [c for host, c in net if host == SITE_HOST]
if site and all(unanswered(c) for c in site):
    bad("audit", f"{SITE_HOST} gave no usable answer to any of {len(site)} requests, so the mirrors weren't really checked")

print("\n".join(problems) if problems else "No problems found.")
if notes:
    print("\nNot counted as problems:")
    print("\n".join(f"  {n}" for n in notes))
print(f"\n{len(apps)} apps, {len(programs)} programs, {len(problems)} problem(s), {len(notes)} note(s).")
sys.exit(1 if problems else 0)
