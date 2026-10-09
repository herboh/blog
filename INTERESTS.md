# Interests profile

`/interests/` is an entirely static Hugo page. Python collects history separately;
Hugo never contacts an API. Film/TV tabs, expandable shelves, and small reveal
animations enhance already-rendered HTML. Without JavaScript both watching shelves
and native disclosures remain usable. Reduced-motion preferences disable animation.
The existing books page and data remain the reading source.

## Credentials

In the checkout that will run the collector:

```sh
mkdir -p .local
# Create privately, without overwriting an existing credentials file.
(umask 077; test -e .local/interests.env || cp scripts/interests.example.env .local/interests.env)
chmod 600 .local/interests.env
$EDITOR .local/interests.env
```

The parser reads literal `NAME=value` lines; it does not execute shell code.
Environment variables can override file values. Do not paste keys into Hugo data,
front matter, commands/URLs in chat, or a public CI log. `.local/` is already ignored.

| Source | Fields in `.local/interests.env` | Where to obtain them |
| --- | --- | --- |
| Music | `LASTFM_API_KEY`, `LASTFM_USERNAME` | [Create a Last.fm API account](https://www.last.fm/api/account/create). No shared secret is needed for reading history. |
| Games | `STEAM_API_KEY`, `STEAM_ID` | [Steam Web API key](https://steamcommunity.com/dev/apikey); your numeric 64-bit Steam ID. Use your own account's key and test with existing privacy settings first. |
| Plex TV / movies | `TAUTULLI_URL`, `TAUTULLI_API_KEY`, `TAUTULLI_USER_ID` | Tautulli Settings → Web Interface → API key. Use the Plex numeric user ID (not a username or server ID). The Users page links to the selected user's details; its `user_id` identifies them. |
| Letterboxd | `LETTERBOXD_USERNAME` | Your username; the public RSS feed and profile favorites need no API key. |

Use Tautulli's reachable base URL including its HTTP root, if configured. Collection
should run where that private service is reachable. There is no need to expose it
publicly or provide a Plex token. `TAUTULLI_AUTH=header` requires Tautulli 2.18+;
older versions can use `TAUTULLI_AUTH=query`. Query authentication may be recorded
by the service/proxy, so prefer header authentication when available.

Blank providers are skipped. Partially configured providers report an error and
retain saved data. Changing an account identifier refuses to merge histories;
use a separate `--state-dir` for another account. Keep one collector/state directory
as authoritative when moving the collector between machines.

Spotify keys are not required: use Last.fm for listening history, including Spotify
listening if scrobbling is enabled in Last.fm's applications settings. This collector
does not obtain Spotify's private Wrapped data or reconstruct listens never scrobbled.

## First run and daily updates

```sh
python3 scripts/refresh_interests.py
```

This collects configured sources, writes `data/interests.json`, exports the current
Git commit, and overlays only that public snapshot and its selected cached artwork. It
builds the export in a temporary directory, runs the site's offline checks, and promotes the validated result to
`.local/interests-site/`. The previous local release is retained at
`.local/interests-site.previous/`. It **does not deploy or change production**.
The deployment review in `SETUP.md` still applies. Untracked/ignored drafts never
enter the export. Commit source/template changes before running this release builder;
ordinary data refreshes do not require a new commit. A private manifest records the
source revision, Hugo version, and public data hash.
Only the generated release receives web-readable permissions (files `644`,
directories `755`); credential and history permissions remain private. Copy the
release into the web server's existing served directory, not the private `.local/`
parent. The runner rejects custom `--output` paths; use the collector directly for
those so a different snapshot cannot silently be substituted during the build.

Useful collector commands:

```sh
# No network; regenerate the page data from saved history + the bookshelf.
python3 scripts/sync_interests.py --offline
# Only one service; unrelated providers keep their saved data.
python3 scripts/sync_interests.py --source steam
# A larger page budget for initial backfill.
python3 scripts/sync_interests.py --source lastfm --max-pages 100
# Paths may be explicit when running from a temporary feature checkout.
python3 scripts/sync_interests.py --env-file /private/path/interests.env --state-dir /private/path/history
```

Exit status: **0** success, **2** one or more providers failed but a valid snapshot
was exported, **1** configuration/storage/export failure. The refresh runner still
builds on status 2. Keep cron logging/alerts for nonzero exits; retries are bounded.
Two collectors cannot write the same state directory concurrently.

Example cron entry after replacing `/path/to/blog` with the permanent checkout and filling credentials:

```cron
PATH=/usr/local/bin:/usr/bin:/bin
17 */6 * * * cd /path/to/blog && /usr/bin/python3 scripts/refresh_interests.py >> .local/interests-refresh.log 2>&1
```

This refreshes the local release every six hours. No schedule is installed by this
change, and that release is not automatically copied to a web server.
Enable publication only after reviewing the generated page and deployment changes.
A user systemd timer can run the same command if persistent missed-run handling is preferred.

## What is kept over time

- `.local/interests/history.sqlite3`: private normalized events, Steam snapshots,
  source identity fingerprints, collection status, and run history. This is the
  authoritative history. No API keys, IP addresses, player devices, Plex usernames,
  or original response bodies are stored in it.
- `.local/interests/history.previous.sqlite3`: consistent SQLite backup taken before
  each run. This is one recovery checkpoint, not a complete backup policy. Back up
  the state directory to your normal private/off-machine backups. Back up the
  credential file separately and securely.
- `data/interests.json`: version 2 public selections for Hugo: titles, album names,
  film release years, artwork, work links, and optional editorial notes. It contains
  no watch dates, play counts, source status, profile links, or account identifiers.
- `.local/interests/artwork/`: private provider artwork cache. Plex poster requests
  are bounded (12 films and 24 TV shows per run); public CDN image requests are also
  bounded. Cover failures do not invalidate history or selections.
- `static/images/interests/`: only artwork referenced by the current snapshot.
  Album covers, film/TV posters and game headers are cached locally. Visitors make
  no provider API or artwork requests. Offline runs reuse the cache; unavailable
  artwork becomes a typographic fallback. Changing selections prunes generated
  public files but retains the private originals. Hand-authored assets are untouched.

Each provider is fetched and validated before its database transaction commits.
Malformed payloads, missing fields, pagination failure, and empty/inaccessible Steam
libraries never replace successful history. Public JSON is written with atomic
replacement. Sources fail independently. On failure, saved history and selections remain available. Source status and
successful-sync timestamps stay in private state and command output.

History is retained, including records later removed upstream. Fetches deduplicate
by stable event identities. Correcting/removing historical records deliberately
requires an archive edit/import workflow; deletion upstream is not an automatic
public purge. Unchanged feeds are not evidence of a complete archive.

## What appears on the page

**Films:** the four favorites on the Letterboxd profile lead. “Lately” uses the three
most recent distinct completed movie plays from Tautulli for the configured user;
saved Plex history remains during outages. Before any Plex movie history has been
collected, dated Letterboxd diary films provide a fallback. If no favorites have ever been saved, rated
diary films are a fallback labeled “Highly rated.” Favorites come from public profile
HTML, so bot protection or markup changes can prevent refresh; the last successful
selection remains. One failed poster request does not discard the selection. The
profile parser also accepts saved HTML through `favorites_from_html` for recovery.
The RSS feed is a recent window, not a historical export. Backfill with an extracted
`diary.csv` from [Letterboxd's export](https://letterboxd.com/settings/data/):

```sh
python3 scripts/sync_interests.py --letterboxd-diary /private/path/diary.csv
```

Set `LETTERBOXD_USERNAME` first to bind the archive to the same account. Keep exports
outside `static/` and Git. CSV and RSS share a title/year/watch-date identity. Repeat
imports preserve RSS artwork and work links. Full review text is not yet displayed.

**TV:** completed episode plays from Tautulli rank series, with the three most recently
watched distinct series below. Only the configured numeric user is accepted. At least
85% completion is required; resumed sessions share a reference ID. This reflects
retained Tautulli history, not every show ever watched. Larger archives need a larger
`--max-pages` budget (100 rows/page); `--source tautulli_tv` collects only TV.
Plex provides posters first. Missing posters use exact, unambiguous title matches from
[TVmaze](https://www.tvmaze.com/api); those cards link back to the matched TVmaze page
for attribution. Ambiguous titles keep their fallback until supplied manually.

Add optional picks to `data/interests_config.toml` to place them ahead of the ranking:

```toml
[[show_picks]]
title = "A show I love"
# Existing titles reuse the saved poster. For an untracked title:
image = "/images/shows/my-show.jpg" # file at static/images/shows/my-show.jpg
note = "An optional personal line."
```

**Music:** the first three artists in Last.fm's `user.getTopArtists` overall chart,
expandable to twelve, with three most recently played distinct artists underneath.
Overall ranking comes directly from the account chart, independently of partial
scrobble backfill. Album covers represent actual albums and are labeled accordingly;
generic artist placeholder images are rejected. The chart does not imply personally
curated favorites. No additional API key is needed for artwork.

**Games:** the first three games by Steam lifetime playtime, expandable to twelve,
and the top three in Steam's rolling two-week window. Hours are used for sorting
but not displayed. `exclude_steam_apps = [123, 456]` removes those app IDs from both
selections. `include_steam_apps` can instead define a public allowlist. An app's store
link contains its ID. Games absent from the newest library also stay out; historic
snapshots remain private. The collector still stores lifetime snapshots for future
analysis without inventing older play sessions.

**Books:** the existing `data/books.toml` supplies reading order, authors and notes;
its first three entries lead, with the rest expandable. Recent reads follow that
file's order. They are labeled as a bookshelf, not invented personal favorites.
The current cover sync enriches metadata; it does not synchronize a reading account.

## Validation

Review `data/interests.json` and all expanded selections before publication:
collapsed content is still public HTML. Steam exclusions do not filter films or
music. Keep actual preview snapshots in an ignored private export until ready to
publish. The planned About/Writing/Projects navigation and CV changes remain separate.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/refresh_interests.py --offline
node --check themes/dark-minimal/assets/js/interests.js
hugo --cleanDestinationDir --panicOnWarning
python3 scripts/check_site.py public
```

The tests mock provider responses to exercise retention, deduplication, pagination,
account filtering, time zones, Steam counter corrections, atomic writes, private
poster selection, CSV re-imports, release permissions and output privacy.
Successful offline tests do not establish that real credentials or remote
services work. Verify a real first collection and inspect `data/interests.json` before
publishing. API references: [Last.fm](https://www.last.fm/api/show/user.getRecentTracks),
[Steam](https://partner.steamgames.com/doc/webapi/IPlayerService),
[Tautulli](https://github.com/Tautulli/Tautulli/wiki/Tautulli-API-Reference),
[Letterboxd](https://letterboxd.com/api-beta/).
