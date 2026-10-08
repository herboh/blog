"""Build the allowlisted public view. No account identifiers leave this module."""
import json
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .storage import get_meta


LABELS = {"lastfm": "Last.fm", "steam": "Steam", "tautulli": "Plex · Tautulli", "letterboxd": "Letterboxd"}


def stamp(value):
    return datetime.fromtimestamp(value, ZoneInfo("UTC")).isoformat().replace("+00:00", "Z") if value else ""


def date(value, tz):
    return datetime.fromtimestamp(value, tz).strftime("%Y-%m-%d")


def public_item(row, metric="", value=0, when=""):
    return {"title": row["title"], "creator": row.get("creator", ""),
        "image": row.get("image", ""), "url": row.get("url", ""),
        "metric": metric, "value": value, "date": when}


def source_info(db, source, now):
    meta = get_meta(db, source, {})
    last = meta.get("last_success", 0)
    status = "pending"
    if last:
        status = "saved" if meta.get("failed") or now - last > 3 * 86400 else "current"
    return {"source": LABELS[source], "status": status, "as_of": stamp(last)}


def periods(events, tz, now):
    years = sorted({date(e["occurred"], tz)[:4] for e in events}, reverse=True)
    return [("recent", "Last 30 days", [e for e in events if now - 30 * 86400 <= e["occurred"] <= now]),
            ("all", "All recorded", events)] + [(y, y, [e for e in events if date(e["occurred"], tz).startswith(y)]) for y in years]


def monthly(events, tz):
    counts = Counter(date(e["occurred"], tz)[:7] for e in events)
    return [{"label": key, "value": counts[key]} for key in sorted(counts)[-12:]]


def event_section(db, source, key, title, now, tz):
    events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM events WHERE source=? ORDER BY occurred DESC,id", (source,))]
    meta = get_meta(db, source, {})
    asof = meta.get("last_success", now)
    events = [e for e in events if e["occurred"] <= asof]
    covers = get_meta(db, "covers", {})
    for event in events:
        if source + ":" + event["item"] in covers:
            event["image"] = covers[source + ":" + event["item"]]
    music = key == "music"
    section = dict(key=key, title=title, **source_info(db, source, now), periods=[], favorites=[])
    section["coverage"] = "No listening history collected yet." if music else "No viewing history collected yet."
    if events:
        section["coverage"] = f"Recorded since {date(min(e['occurred'] for e in events), tz)}."
        if source == "lastfm" and not meta.get("history_complete"):
            section["coverage"] += " Older listening history is still being collected; totals cover saved records."
        if source == "tautulli":
            section["coverage"] += " Completed Plex movie plays (at least 85%); resumed sessions are grouped."
        if source == "letterboxd":
            section["coverage"] += " Diary import + recent feed." if meta.get("imported_diary") else " Recent diary feed only; older watches may be missing."
    for ident, label, subset in periods(events, tz, asof):
        counts = Counter(e["item"] for e in subset)
        latest = {e["item"]: e for e in reversed(subset)}
        ranked = sorted(counts, key=lambda k: (-counts[k], latest[k]["title"].casefold()))
        unit = "plays" if music else "watches"
        # Recent films are a diary, while all/year views show most watched.
        if not music and ident == "recent":
            items = [public_item(e, "★ " + str(e["rating"]) + "/5" if e.get("rating") is not None else "Watched", when=date(e["occurred"], tz)) for e in subset[:12]]
            heading = "Recently watched"
        else:
            items = [public_item(latest[k], f"{counts[k]:,} {unit}", counts[k]) for k in ranked[:12]]
            heading = "Most played tracks" if music else "Most watched films"
        metrics = [{"value": f"{len(subset):,}", "label": unit}, {"value": str(len(counts)), "label": "tracks" if music else "films"}]
        if music:
            metrics.append({"value": str(len({e["creator"] for e in subset})), "label": "artists"})
        p = dict(id=ident, label=label, heading=heading, metrics=metrics, items=items,
                 series=monthly(subset, tz), series_label=f"{unit.capitalize()} by month · latest 12 recorded months",
                 note="Scrobbles count plays, not listening minutes. Rolling periods end at the last successful sync." if music else "Viewing frequency is separate from a favorite or a rating. Rolling periods end at the last successful sync.")
        if music:
            artists = Counter(e["creator"] for e in subset)
            p["secondary"] = [{"title": artist, "metric": f"{count:,} plays"} for artist, count in artists.most_common(5)]
        section["periods"].append(p)
    # Ratings, when available, are useful as a separate all-time list.
    rated = {}
    for e in reversed(events):
        if e.get("rating") is not None:
            rated[e["item"]] = e
    section["rated"] = [public_item(e, f"★ {e['rating']:g}/5") for e in sorted(rated.values(), key=lambda e: (-e["rating"], e["title"]))[:6]]
    return section


def steam_section(db, config, now, tz):
    meta = get_meta(db, "steam", {})
    section = dict(key="games", title="Playing", **source_info(db, "steam", now), periods=[], favorites=[])
    rows = db.execute("SELECT * FROM snapshots ORDER BY observed,appid").fetchall()
    include = {str(x) for x in config.get("include_steam_apps", [])}
    exclude = {str(x) for x in config.get("exclude_steam_apps", [])}
    allowed = lambda app: app not in exclude and (not include or app in include)
    # Use the most recent library as the publication boundary. Old snapshots remain private.
    newest = max((r["observed"] for r in rows), default=0)
    active = {r["appid"] for r in rows if r["observed"] == newest and allowed(r["appid"])}
    previous, latest, deltas = {}, {}, []
    corrections = 0
    gaps = 0
    for row in rows:
        app = row["appid"]
        if app not in active:
            continue
        item = json.loads(row["payload"])
        item["creator"] = ""
        latest[app] = item
        if app in previous:
            old = previous[app]
            change = row["minutes"] - old["minutes"]
            if change < 0:
                corrections += 1  # Reset baseline; never add the whole lifetime total.
            elif change:
                deltas.append(dict(occurred=row["observed"], item=app, minutes=change))
                if row["observed"] - old["observed"] > 36 * 3600:
                    gaps += 1
        previous[app] = row
    first = meta.get("first_observed")
    section["coverage"] = f"Yearly tracking began {date(first, tz)}. Increases are assigned to the date observed, so delayed updates can cross month or year boundaries." if first else "No playtime snapshot collected yet."
    if gaps:
        section["coverage"] += " Some increases span collection gaps."
    if corrections:
        section["coverage"] += " Steam playtime corrections were excluded from increases."
    years = sorted({date(r["observed"], tz)[:4] for r in rows}, reverse=True)
    for ident, label in [("recent", "Last 2 weeks"), ("all", "All time")] + [(y, y) for y in years]:
        counts = Counter()
        series = []
        if ident in ("all", "recent"):
            field = "minutes" if ident == "all" else "recent_minutes"
            counts.update({app: item[field] for app, item in latest.items() if item[field] > 0})
            note = "Lifetime playtime returned by Steam." if ident == "all" else "Steam's rolling two-week totals at the last successful sync."
        else:
            subset = [d for d in deltas if date(d["occurred"], tz).startswith(ident)]
            months = Counter()
            for event in subset:
                counts[event["item"]] += event["minutes"]
                months[date(event["occurred"], tz)[:7]] += event["minutes"]
            series = [{"label": month, "value": round(minutes / 60, 1)} for month, minutes in sorted(months.items())]
            note = "Observed playtime increases only; the initial lifetime total is excluded."
        ordered = sorted(counts, key=lambda app: (-counts[app], latest[app]["title"]))
        items = [public_item(latest[app], f"{counts[app] / 60:,.1f} hrs", round(counts[app] / 60, 1)) for app in ordered[:12]]
        section["periods"].append(dict(id=ident, label=label, heading="Most played games", items=items,
            metrics=[{"value": f"{sum(counts.values()) / 60:,.1f}", "label": "hours"}, {"value": str(len(counts)), "label": "games played"}],
            series=series, series_label="Observed hours by month", note=note))
    return section


def book_section(root):
    import tomllib
    from sync_books import book_key
    entries = tomllib.loads((root / "data/books.toml").read_text()).get("books", [])
    cache_path = root / "data/books_cache.json"
    cache = json.loads(cache_path.read_text()).get("books", {}) if cache_path.exists() else {}
    providers = set()
    for record in cache.values():
        source = record.get("cover_source", "")
        if source.startswith("openlibrary"):
            providers.add("Open Library")
        elif source == "hardcover":
            providers.add("Hardcover")
    attribution = "Reading log" + (" · " + " / ".join(sorted(providers)) if providers else "")
    section = dict(key="books", title="Reading", source=attribution,
        status="local", as_of="", coverage="From my bookshelf, grouped by reading year. Exact finish dates are not recorded.",
        periods=[], favorites=[])
    years = sorted({str(e["year_read"]) for e in entries if e.get("year_read")}, reverse=True)
    for ident, label in [("recent", "Latest reads"), ("all", "All books")] + [(y, y) for y in years]:
        subset = entries if ident == "all" else entries[:6] if ident == "recent" else [e for e in entries if str(e.get("year_read")) == ident]
        items = []
        for row in subset:
            record = cache.get(book_key(row), {})
            cover = row.get("cover_file") or record.get("cover_image", "")
            item = dict(title=row.get("title", record.get("title", "Untitled")), creator=row.get("author", record.get("author", "")), image=cover, url="/books/")
            metric = f"{row['rating']}/5" if row.get("rating") else str(row.get("year_read", ""))
            items.append(public_item(item, metric))
        section["periods"].append(dict(id=ident, label=label, heading="On the bookshelf", items=items,
            metrics=[{"value": str(len(subset)), "label": "books"}, {"value": str(len({e.get('author') for e in subset})), "label": "authors"}],
            series=[], series_label="", note="Ordered as recorded on my bookshelf."))
    return section


def export(db, root, config, now):
    tz = ZoneInfo(config.get("timezone", "America/New_York"))
    movies = config.get("movies_source", "auto")
    if movies == "auto":
        movies = "tautulli" if get_meta(db, "tautulli", {}).get("last_success") else "letterboxd"
    if movies not in ("tautulli", "letterboxd"):
        raise ValueError("movies_source must be auto, tautulli, or letterboxd")
    sections = [event_section(db, "lastfm", "music", "Listening", now, tz),
        steam_section(db, config, now, tz), book_section(root),
        event_section(db, movies, "movies", "Watching", now, tz)]
    for favorite in config.get("favorites", []):
        for section in sections:
            if section["key"] == favorite["kind"]:
                # Editorial URLs must also be public HTTP(S), not credential-bearing.
                from urllib.parse import urlsplit
                url = favorite.get("url", "")
                parts = urlsplit(url)
                if url and (parts.scheme != "https" or parts.username or parts.query):
                    raise ValueError("Favorite links must be public HTTPS URLs without credentials or queries")
                section["favorites"].append({"title": favorite["title"], "note": favorite.get("note", ""), "url": url})
    # Restoring a database without its artwork must still produce a valid site.
    static = (root / "static").resolve()
    for section in sections:
        items = [item for period in section["periods"] for item in period["items"]]
        items.extend(section.get("rated", []))
        for item in items:
            if item["image"].startswith("/"):
                asset = (static / item["image"].lstrip("/")).resolve()
                if not asset.is_relative_to(static) or not asset.is_file():
                    item["image"] = ""
    return {"version": 1, "sections": sections}
