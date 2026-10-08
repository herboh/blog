# Interests dashboard

`/interests/` is an entirely static Hugo page. Python collects history separately;
Hugo never contacts an API. Period selectors only reveal HTML already in the page.
The existing books page and data remain the reading source.

## Credentials

In the checkout that will run the collector:

```sh
mkdir -p .local
cp scripts/interests.example.env .local/interests.env
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
| Plex movies | `TAUTULLI_URL`, `TAUTULLI_API_KEY`, `TAUTULLI_USER_ID` | Tautulli Settings → Web Interface → API key. Use the Plex numeric user ID (not a username or server ID). The Users page links to the selected user's details; its `user_id` identifies them. |
| Letterboxd | `LETTERBOXD_USERNAME` | Your username; the public RSS feed needs no API key. |

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
Git commit, and overlays only that public snapshot and its cached movie posters. It
builds the export in a temporary directory, runs the site's offline checks, and promotes the validated result to
`.local/interests-site/`. The previous local release is retained at
`.local/interests-site.previous/`. It **does not deploy or change production**.
The deployment review in `SETUP.md` still applies. Untracked/ignored drafts never
enter the export. Commit source/template changes before running this release builder;
ordinary data refreshes do not require a new commit. A private manifest records the
source revision, Hugo version, and public data hash.

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
- `data/interests.json`: allowlisted public projection for Hugo. Safe to review and
  commit with the site. It contains titles, artwork, work links, aggregates, dates,
  and successful-sync timestamps. No profile links or account identifiers.
- `static/images/interests/`: public cached Tautulli posters. Up to 12 missing covers
  are fetched per run; cover failures do not fail movie collection. Music/game
  artwork uses public CDN URLs with a visual fallback if unavailable.

Each provider is fetched and validated before its database transaction commits.
Malformed payloads, missing fields, pagination failure, and empty/inaccessible Steam
libraries never replace successful history. Public JSON is written with atomic
replacement. Sources fail independently. On a failure the page keeps the previous
successful timestamp, marks the source as saved, and keeps rolling periods anchored
to that successful collection. Offline builds do not manufacture fresh sync dates.

History is retained, including records later removed upstream. Fetches deduplicate
by stable event identities. Correcting/removing historical records deliberately
requires an archive edit/import workflow; deletion upstream is not an automatic
public purge. Unchanged feeds are not evidence of a complete archive.

## Meaning of each view

**Music:** recent means 30 days ending at the last successful sync. Rank tracks and
artists by recorded scrobbles; do not label play counts as listening minutes. Initial
backfill saves a bounded batch, then resumes older history on later runs. New listens
are collected with a seven-day overlap. Counts are labeled **All recorded** and
coverage says when older history is still being collected. If new activity exceeds
the page budget, the collector fails without advancing its watermark; increase
`--max-pages`. Historical corrections outside the overlap require a deliberate rescan.

**Games:** All time is lifetime hours from Steam; Last 2 weeks is Steam's rolling
window. Yearly views sum positive changes in cumulative hours after the first
snapshot. New games establish their own baseline. Counter decreases reset the
baseline without adding spurious hours. Increases are assigned to collection time,
not invented session times; offline synchronization and missed runs can shift a
change across a month/year boundary. Coverage labels the tracking start and gaps.
App IDs excluded in `data/interests_config.toml` are omitted from every measured public list,
chart and total. Games absent from the newest library also stay out of the export;
old snapshots remain private. Steam hours are time reported by Steam, not verified
active attention.

**Books:** the existing `data/books.toml` is authoritative for reading years, order,
ratings and notes. The current cover sync enriches metadata; it does not synchronize
a reading-service account. Latest reads follow that file's order, not invented dates.

**Movies:** by default, use Tautulli once it has successfully collected; otherwise use
Letterboxd. Set `movies_source = "tautulli"` or `"letterboxd"` in the public config
to pin the source. They are never summed together. Tautulli requires one explicit
user ID, verifies that every response row matches, excludes non-movies and unfinished
plays, requires at least 85% completion, and groups resumed playbacks by reference ID using the latest qualifying completion date.
All recorded means the watch history Tautulli still retains, not all films ever seen.
Large archives exceeding 2,000 rows need a larger `--max-pages` value (100 rows/page).
The first version scans retained movie history on each run so updated session records
can be reconciled without inventing a reliable modified-since cursor.

Letterboxd collects dated diary entries from RSS. Lists and undated reviews are
ignored. A feed is a recent window, not a historical export. Backfill with an extracted
`diary.csv` from [Letterboxd's export](https://letterboxd.com/settings/data/):

```sh
python3 scripts/sync_interests.py --letterboxd-diary /private/path/diary.csv
```

Set `LETTERBOXD_USERNAME` before importing so the archive is bound to the same account as the feed. Keep exports outside `static/` and Git. CSV and RSS share a title/year/watch-date key,
so repeat imports do not duplicate watches. Multiple watches of the exact same film
on the same day collapse to one. Highest rated is shown separately when diary ratings
exist. A feed gap longer than the feed window needs another export/import.

**Favorites:** use `[[favorites]]` entries in `data/interests_config.toml`. These are
editorial picks with optional notes and work links; most played and most watched
are labeled as measured rankings. No favorites are fabricated from unprovided ratings.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 scripts/refresh_interests.py --offline
node --check themes/dark-minimal/assets/js/interests.js
hugo --cleanDestinationDir --panicOnWarning
python3 scripts/check_site.py public
```

The tests mock provider responses to exercise retention, deduplication, pagination,
account filtering, time zones, Steam counter corrections, atomic writes and output
privacy. Successful offline tests do not establish that real credentials or remote
services work. Verify a real first collection and inspect `data/interests.json` before
publishing. API references: [Last.fm](https://www.last.fm/api/show/user.getRecentTracks),
[Steam](https://partner.steamgames.com/doc/webapi/IPlayerService),
[Tautulli](https://github.com/Tautulli/Tautulli/wiki/Tautulli-API-Reference),
[Letterboxd](https://letterboxd.com/api-beta/).
