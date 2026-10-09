# chanfulmer.com

A static Hugo site with a custom `dark-minimal` theme. There is no application
server, npm install, or Docker image build required for the site itself.

## Source layout

| Path | Purpose |
| --- | --- |
| `hugo.toml` | Site configuration and navigation |
| `content/` | Published posts and pages |
| `layouts/` | Site-specific page templates |
| `themes/dark-minimal/` | Shared templates, CSS, and JavaScript |
| `data/books.toml` | Bookshelf entries |
| `data/books_cache.json` | Saved book metadata and local cover paths |
| `static/` | Published images and book covers |
| `scripts/sync_books.py` | Optional metadata and cover refresh |
| `scripts/check_site.py` | Offline generated-site validation |
| `public/` | Generated output, ignored by Git |
| `.local/` | Private local notes, previews, caches, and release artifacts |

Book metadata and cover images are committed, so normal builds need no external
API calls. The optional cover sync requires Python 3.11+ and network access.
Use `python3 scripts/sync_books.py --help` for options; any credentials belong
in environment variables, never in Git.

## Develop and verify

The current baseline is verified with Hugo 0.167.0 extended. Python 3.11+ is
used for the helper scripts; Node is optional for the JavaScript syntax check.

```sh
hugo server --bind 127.0.0.1 --port 1313 --disableFastRender \
  --destination "$PWD/.local/preview" --cacheDir "$PWD/.local/hugo-cache"
```

Open <http://localhost:1313/>. Add `-D` only when intentionally previewing drafts.

Before committing:

```sh
hugo --cleanDestinationDir --panicOnWarning --cacheDir "$PWD/.local/hugo-cache"
python3 scripts/check_site.py public
node --check themes/dark-minimal/assets/js/main.js
git diff --check
```

The offline checker validates local links, assets, fragments, and XML. It does
not test external links or browser interactions. Check the mobile menu, article
layouts, and bookshelf in a browser too.

## Publishing

Build releases from an export of the chosen Git commit, with drafts excluded,
then validate the generated output before publishing it. Keep the previous
artifact and record the commit, Hugo version, and file hashes for rollback.
CSS and JavaScript filenames include content hashes to avoid stale assets.

This repository is public. Unpublished local drafts, private recovery history,
credentials, and deployment notes must stay outside the published history.
The ignored audio draft is excluded from production builds exported from Git.
Private deployment and recovery instructions are maintained separately in
`.local/DEPLOYMENT.md`; they are intentionally not part of this repository.

## Baseline checks

The baseline without the unpublished audio post contains 16 HTML pages, 241
checked local references, and 14 XML files. Hugo's warning-as-error build,
JavaScript/Python syntax, and desktop/mobile browser checks pass. The bookshelf
contains 22 entries with local covers. The CV remains a placeholder pending the
next design revision.

## Interests profile

The static `/interests/` page reads `data/interests.json`. Collection is separate
from Hugo and keeps normalized history in a private SQLite database. See
[INTERESTS.md](INTERESTS.md) for credentials, initial backfill, source coverage,
failure behavior, and the optional cron command. `scripts/refresh_interests.py`
prepares a checked local release from a Git export; it does not deploy it.
