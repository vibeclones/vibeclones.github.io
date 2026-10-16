# vibeclones.github.io

Catalog hub for the Vibeclones org. It holds only the catalog; each clone lives in its own repo and is served by that repo's GitHub Pages.

## Layout

- `catalog.json` is the source of truth: categories, apps, clones, versions.
- `index.html` renders it, grouped by category then type.

## Adding an app

1. Create a repo `vibeclones/<slug>` and enable Pages.
2. Add an entry to `apps` in `catalog.json`:
   - `category`: one of the ids in `categories`
   - `type`: free text (spreadsheet, CAD, ...)
   - `clones`: apps it imitates; one entry = single-app clone, several = multi-app
   - `latest` / `versions`: release names, newest first in `versions`

## URL scheme (inside each app repo's Pages site)

- `/<slug>/latest/` redirects to the newest release
- `/<slug>/v<version>/` is a frozen copy of that release

Old versions count toward the ~1 GB Pages limit per repo; prune the oldest if needed.
