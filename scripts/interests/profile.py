"""Small visitor-facing selections; operational metadata stays out of this view."""
import json
from collections import Counter

from .storage import get_meta


def card(item, subtitle=None):
    return {"title": item["title"], "subtitle": subtitle if subtitle is not None else item.get("subtitle", item.get("creator", "")),
            "image": item.get("image", ""), "url": item.get("url", ""), "note": item.get("note", "")}


def unique(items):
    seen = set()
    result = []
    for item in items:
        key = item["title"].casefold()
        if key not in seen:
            seen.add(key)
            result.append(card(item))
    return result


def events(db, source):
    covers = get_meta(db, "covers", {})
    rows = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE source=? ORDER BY occurred DESC,id", (source,))]
    for row in rows:
        row["image"] = covers.get(source + ":" + row["item"], row.get("image", ""))
    return rows


def build(db, sections, config):
    legacy = {s["key"]: s for s in sections}
    films = events(db, "letterboxd")
    # Favorites reflect Letterboxd picks; recent viewing follows completed Plex plays.
    # Keep saved Plex history on outages, falling back only before it has any entries.
    recent_films = events(db, "tautulli") or films
    rated = sorted([e for e in films if e.get("rating") is not None], key=lambda e: -e["rating"])
    favorites = get_meta(db, "film_favorites", [])
    shows = events(db, "tautulli_tv")
    counts = Counter(e["item"] for e in shows)
    latest = {e["item"]: e for e in reversed(shows)}
    ranked = [latest[k] for k in sorted(counts, key=lambda k: (-counts[k], latest[k]["title"]))]
    show_picks = config.get("show_picks", [])
    by_title = {s["title"].casefold(): s for s in ranked}
    manual = []
    for pick in show_picks:
        saved = by_title.get(pick["title"].casefold(), {})
        manual.append({**saved, **pick, "image": pick.get("image") or saved.get("image", "")})
    music = get_meta(db, "music_selection", {})
    game_periods = {p["id"]: p["items"] for p in legacy["games"]["periods"]}
    book_periods = {p["id"]: p["items"] for p in legacy["books"]["periods"]}
    films_view = {"key": "films", "title": "Films", "label": "Favorites" if favorites else "Highly rated",
                  "items": unique(favorites or rated)[:12], "recent": unique(recent_films)[:3], "more_label": "More films"}
    shows_view = {"key": "shows", "title": "TV", "label": "The regulars",
                  "items": [card(s, "") for s in unique([*manual, *ranked])[:12]],
                  "recent": [card(s, "") for s in unique(shows)[:3]], "more_label": "More shows"}
    return {"watching": [films_view, shows_view], "shelves": [
        {"key": "music", "title": "Music", "label": "All-time rotation", "items": unique(music.get("artists", []))[:12],
         "recent": unique(music.get("recent", []))[:3], "more_label": "More artists"},
        {"key": "games", "title": "Games", "label": "Most played", "items": [card(i, "") for i in game_periods["all"]][:12],
         "recent": [card(i, "") for i in game_periods["recent"]][:3], "more_label": "More games"},
        {"key": "books", "title": "Books", "label": "On my shelf", "items": [card(i) for i in book_periods["all"]],
         "recent": [card(i) for i in book_periods["recent"]][:3], "more_label": "The rest of the bookshelf"},
    ]}
