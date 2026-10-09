"""Optional profile/artwork enrichment. Failures keep the last successful selection."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

from .sources import fetch, FetchError, image_url, film_link, require_list
from .storage import get_meta, set_meta


def lastfm_call(env, method, **params):
    reply = fetch("https://ws.audioscrobbler.com/2.0/", {
        "api_key": env["LASTFM_API_KEY"], "user": env["LASTFM_USERNAME"],
        "method": method, "format": "json", **params})
    if "error" in reply:
        raise FetchError("Last.fm selection unavailable; retaining saved selections")
    return reply


def album_art(row):
    return next((image_url(i.get("#text")) for i in reversed(row.get("image", [])) if image_url(i.get("#text"))), "")


def music_selection(env, events):
    albums = require_list(lastfm_call(env, "user.gettopalbums", period="overall", limit=100)["topalbums"]["album"])
    artists = require_list(lastfm_call(env, "user.gettopartists", period="overall", limit=12)["topartists"]["artist"])
    covers = {}
    for album in albums:
        artist = album["artist"]["name"]
        if artist.casefold() not in covers and album_art(album):
            covers[artist.casefold()] = {"image": album_art(album), "album": album["name"]}
    latest = []
    seen = set()
    for event in events:
        artist = event["creator"]
        if not event.get("album") or artist.casefold() in seen:
            continue
        seen.add(artist.casefold())
        latest.append({"title": artist, "subtitle": event["album"], "image": event.get("image", ""),
                       "url": "https://www.last.fm/music/" + quote(artist, safe="")})
        if len(latest) == 3:
            break
    # An album image represents a record, never an invented artist portrait.
    for row in artists:
        name = row["name"]
        if name.casefold() not in covers:
            match = next((e for e in events if e["creator"].casefold() == name.casefold() and e.get("album")), None)
            if match:
                covers[name.casefold()] = {"image": match.get("image", ""), "album": match["album"]}
    def fill_art(artist, album, image):
        if image or not album:
            return image
        try:
            return album_art(lastfm_call(env, "album.getinfo", artist=artist, album=album)["album"])
        except (FetchError, KeyError, TypeError, ValueError):
            return ""
    for name, cover in covers.items():
        cover["image"] = fill_art(name, cover["album"], cover["image"])
    for item in latest:
        item["image"] = fill_art(item["title"], item["subtitle"], item["image"])
    def cards(rows):
        return [{"title": row["name"], "subtitle": covers.get(row["name"].casefold(), {}).get("album", ""),
                 "image": covers.get(row["name"].casefold(), {}).get("image", ""),
                 "url": "https://www.last.fm/music/" + quote(row["name"], safe="")} for row in rows]
    return {"artists": cards(artists), "recent": latest}


class LetterboxdPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_favorites = False
        self.favorites_seen = False
        self.favorites = []
        self.in_json = False
        self.json_text = []
        self.documents = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "section" and attrs.get("id") == "favourites":
            self.in_favorites = self.favorites_seen = True
        if self.in_favorites and attrs.get("data-component-class") == "LazyPoster":
            url = film_link("https://letterboxd.com" + attrs.get("data-item-link", ""))
            name = attrs.get("data-item-name", "")
            match = re.fullmatch(r"(.+) \((\d{4})\)", name)
            if url and match:
                self.favorites.append({"title": match[1], "subtitle": match[2], "url": url, "image": ""})
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.in_json = True
            self.json_text = []

    def handle_data(self, data):
        if self.in_json:
            self.json_text.append(data)

    def handle_endtag(self, tag):
        if tag == "section":
            self.in_favorites = False
        if tag == "script" and self.in_json:
            self.in_json = False
            # Letterboxd wraps its JSON-LD in a legacy CDATA comment.
            raw = "".join(self.json_text).strip()
            raw = re.sub(r"^/\*\s*<!\[CDATA\[\s*\*/|/\*\s*\]\]>\s*\*/$", "", raw).strip()
            try:
                self.documents.append(json.loads(raw))
            except ValueError:
                pass


def letterboxd_favorites(env, previous):
    username = env["LETTERBOXD_USERNAME"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", username):
        raise FetchError("Invalid Letterboxd username")
    return favorites_from_html(fetch("https://letterboxd.com/" + username + "/", html=True), previous)


def favorites_from_html(html, previous):
    """Also accepts an already-saved public profile when live HTML is unavailable."""
    page = LetterboxdPage()
    page.feed(html)
    if not page.favorites_seen or not page.favorites:
        raise FetchError("Letterboxd favorites markup unavailable; retaining saved selection")
    saved = {item["url"]: item for item in previous}
    for item in page.favorites[:4]:
        item["image"] = saved.get(item["url"], {}).get("image", "")
        if item["image"]:
            continue
        film = LetterboxdPage()
        try:
            film.feed(fetch(item["url"], html=True))
        except FetchError:
            continue  # One unavailable poster must not discard the favorite selection.
        for doc in film.documents:
            if isinstance(doc, dict) and doc.get("@type") == "Movie":
                image = doc.get("image", "")
                parts = urlsplit(image)
                if parts.scheme == "https" and parts.hostname == "a.ltrbxd.com" and not parts.username:
                    item["image"] = image
    return page.favorites[:4]


def fill_show_art(db, view, online=True):
    """Exact, unambiguous TVmaze matches fill posters lost from the Plex library."""
    saved = get_meta(db, "show_art", {})
    attempted = set()
    for shelf in view["profile"]["watching"]:
        if shelf["key"] != "shows":
            continue
        for item in [*shelf["items"], *shelf["recent"]]:
            if item["image"]:
                continue
            key = item["title"].casefold()
            if key not in saved and key not in attempted and online:
                attempted.add(key)
                try:
                    rows = require_list(fetch("https://api.tvmaze.com/search/shows", {"q": item["title"]}))
                    matches = [r["show"] for r in rows if r["show"]["name"].casefold() == key]
                    if len(matches) == 1:
                        show = matches[0]
                        image = (show.get("image") or {}).get("medium", "")
                        url = show.get("url", "")
                        art, link = urlsplit(image), urlsplit(url)
                        if art.scheme == link.scheme == "https" and art.hostname == "static.tvmaze.com" and link.hostname == "www.tvmaze.com" and not art.username and not link.username:
                            saved[key] = {"image": image, "url": url}
                except (FetchError, KeyError, TypeError, ValueError):
                    pass
            if key in saved:
                # Linking the image/title to the show provides TVmaze attribution.
                item.update(saved[key])
    with db:
        set_meta(db, "show_art", saved)


def enrich(db, env, source):
    jobs = []
    if source in ("all", "lastfm") and not get_meta(db, "lastfm", {}).get("failed", True):
        events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE source='lastfm' ORDER BY occurred DESC")]
        jobs.append(("music_selection", lambda: music_selection(env, events)))
    if source in ("all", "letterboxd") and not get_meta(db, "letterboxd", {}).get("failed", True):
        jobs.append(("film_favorites", lambda: letterboxd_favorites(env, get_meta(db, "film_favorites", []))))
    for key, job in jobs:
        try:
            value = job()
            with db:
                set_meta(db, key, value)
            print(key + ": selection saved")
        except (FetchError, KeyError, TypeError, ValueError, OSError):
            print(key + ": unavailable; keeping saved selection")
