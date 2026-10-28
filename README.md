# Vibeclones

A guide to alternatives to well-known software that the AI era made possible: apps you can open right in your browser. Live at https://vibeclones.github.io.

The apps belong to their authors. This site lists them, groups the ones that replace the same program so you can compare them, and links to the authors' own copies.

## Browser only

- **No sign-in walls.** An app is only listed if it opens and works without an account. Apps that can be tried without signing in (even if signing in adds saving) are fine; apps that open on a "Sign in" page and only offer a demo are not listed.
- **Browser apps are the default.** A row's link opens the app at the author's own hosted address (the `official` field). If an app has no official hosted copy, we host a copy ourselves from its release or source, in its own repo under the [vibeclones](https://github.com/vibeclones) organization.
- **Browser only.** Desktop-only software isn't listed; [remade.wiki](https://remade.wiki/) is a more complete catalog that includes it. An app can also be available as a desktop download, which we only mention in its notes.
- **Older versions.** We keep every version we can. If the author doesn't keep their old versions online, we mirror them ourselves (see "Adding an app"); `noMirror` is only for an author who hosts every version themselves, or an app whose license or releases leave us nothing to copy.

## How the site works

- `index.html` is the whole front end: it reads `catalog.json` and `history.json`, and for each app we host a copy of, `/<slug>/versions.json` from that app's own Pages site.
- `catalog.json` is the list of apps. Fields:
  - `slug`, `name`, `category`, `type`, `description`, `source` (the author's repo), `license`, `notes` (short list of things to know)
  - `by`: the publisher, as `{ name, url, logo? , logoWide? }`
  - `clones`: the programs it replaces, as ids into the top-level `programs` table (may be empty; each program is defined once there, with a short `name` and an optional `full` name such as "Adobe Photoshop", so it can't be listed under two names); `group`: the label used to put apps that replace the same program side by side
  - `featured`: a number; featured groups come first, in order
  - `official`: the author's own hosted web app, if there is one. `officialBy`: who hosts it when that isn't the author (for example `daijro`, whose playground hosts web ports of other people's apps)
  - `versionUrl`: for an author who keeps every version online, the address of one version with `{v}` in place of the version (for example `https://getcadcraft.com/use/modelcraft/{v}`). The history job reads the version list from the author's page, and every version links there. Set `noMirror` too, so no copy of ours is used.
  - `tagPrefix`: the prefix of the author's release tags if it isn't `v`. `releasesFrom`: another repo whose releases are this app's versions (for example a web port). `noMirror`: why we keep no mirror of older versions. Only for an author who keeps every version online, or an app whose license or releases leave nothing to copy; an author who hosts only the newest version is a reason to mirror, not to skip. `trackPath`: see below.
  - `trackPath`: a folder inside the source repo to follow for dated snapshots, for projects with no releases of their own
- `history.json` is written by `scripts/history.py`, run every three hours by `.github/workflows/history.yml`. It records each version's date (and size, where we host a copy). For apps we don't host, it notes versions straight from the author's repo: releases where there are any, otherwise dated snapshots of the latest commit.
- `logos/` holds a few publisher logos that aren't just a GitHub avatar.

## Adding an app

1. Find the author's repo, license, and where (if anywhere) they host the app. An app with no license can be listed and linked, but not copied.
2. Add it to `catalog.json`. For a web app with an `official` address, that's usually all: no repo of ours is needed, and the history job starts recording its versions. Always give the publisher an icon (`by.logo`, normally their GitHub avatar at `https://github.com/<user>.png?size=64`), whether they are an organization or an individual, and a brand color (`PUBCOLOR` in `index.html`) for every publisher without exception: if its avatar has no usable color (a photo, greyscale or near-black), use the accent color of its app (the playground's `tools.yaml` lists one per app) or of its site, never leave it neutral. `python scripts/audit.py` flags any publisher without one.
3. Check whether the author keeps old versions online (a `versionUrl` pattern, or per-version folders on their site). If they do, set `versionUrl` and `noMirror`. If they don't, and the license allows copying, create a mirror repo under the [vibeclones](https://github.com/vibeclones) organization that builds or unpacks each release and publishes `versions.json`, even when the app has an `official` address: the link still goes to the author's copy, and the mirror holds the history. Set `noMirror` only when the license or the releases leave nothing to copy, and say why.

4. After the change is pushed, run the `Record history` workflow (`gh workflow run history.yml -R vibeclones/vibeclones.github.io`) instead of waiting for the three-hourly schedule; until it runs, a new app shows no versions or timeline. Then check its log: the "Audit the data" step lists any app whose upstream releases aren't hosted or explained, and a new mirror may need its own `mirror.yml` run to catch up to the newest release.

Nothing here is affiliated with the products it names; product names belong to their respective owners.
