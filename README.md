# Vibeclones

A guide to alternatives to well-known software that the AI era made possible: mostly apps you can open right in your browser, plus a few standout desktop apps, clearly marked. Live at https://vibeclones.github.io.

The apps belong to their authors. This site lists them, groups the ones that replace the same program so you can compare them, and links to the authors' own copies.

## Browser first, desktop allowed

- **No sign-in walls.** An app is only listed if it opens and works without an account. Apps that can be tried without signing in (even if signing in adds saving) are fine; apps that open on a "Sign in" page and only offer a demo are not listed.
- **Browser apps are the default.** A row's link opens the app at the author's own hosted address (the `official` field). If an app has no official hosted copy, we host a copy ourselves from its release or source, in its own repo under the [vibeclones](https://github.com/vibeclones) organization.
- **Desktop-only apps are allowed, with a warning.** They carry an amber "Desktop only" label on the row and a banner in the details dialog. Their link goes to the author's own download page (`download`), and they have no repo of ours. Their older versions link to the author's releases page.
- **Older versions.** We keep a copy of an older version only where we still host the app. For apps we don't host, the version list is recorded from the author's repo, for reference.

## How the site works

- `index.html` is the whole front end: it reads `catalog.json` and `history.json`, and for each app we host a copy of, `/<slug>/versions.json` from that app's own Pages site.
- `catalog.json` is the list of apps. Fields:
  - `slug`, `name`, `category`, `type`, `description`, `source` (the author's repo), `license`, `notes` (short list of things to know)
  - `by`: the publisher, as `{ name, url, logo? , logoWide? }`
  - `clones`: the programs it replaces, as ids into the top-level `programs` table (may be empty; each program is defined once there, with a short `name` and an optional `full` name such as "Adobe Photoshop", so it can't be listed under two names); `group`: the label used to put apps that replace the same program side by side
  - `featured`: a number; featured groups come first, in order
  - `official`: the author's own hosted web app, if there is one
  - `platform: "desktop"` marks a desktop-only app, with `platforms` (for example `["Windows","macOS","Linux"]`) and `download` (the author's download page). `tagPrefix` is the prefix of the author's release tags if it isn't `v`.
  - `trackPath`: a folder inside the source repo to follow for dated snapshots, for projects with no releases of their own
- `history.json` is written by `scripts/history.py`, run daily by `.github/workflows/history.yml`. It records each version's date (and size, where we host a copy). For apps we don't host, it notes versions straight from the author's repo: releases where there are any, otherwise dated snapshots of the latest commit.
- `logos/` holds a few publisher logos that aren't just a GitHub avatar.

## Adding an app

1. Find the author's repo, license, and where (if anywhere) they host the app. An app with no license can be listed and linked, but not copied.
2. Add it to `catalog.json`. For a web app with an `official` address, that's usually all: no repo of ours is needed, and the history job starts recording its versions.
3. Only if there is no official hosted copy and the license allows it, create a mirror repo that builds or unpacks the release and publishes `versions.json`.

Nothing here is affiliated with the products it names; product names belong to their respective owners.
