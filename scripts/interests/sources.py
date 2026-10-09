"""Read-only providers. Network errors never include URLs, keys, or response bodies."""
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .storage import stable_id


class FetchError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # API requests may contain keys. Do not follow redirects with credentials.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, params=None, headers=None, xml=False, html=False):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "chanfulmer-interests/1.0", **(headers or {})})
    opener = urllib.request.build_opener(NoRedirect)
    for attempt in range(3):
        try:
            with opener.open(request, timeout=25) as response:
                raw = response.read(16_000_001)
            if len(raw) > 16_000_000:
                raise FetchError("Response exceeded size limit")
            return raw.decode("utf-8") if html else ET.fromstring(raw) if xml else json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise FetchError(f"HTTP {exc.code}; previous data retained") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise FetchError("Connection failed; previous data retained") from None
        except (ValueError, ET.ParseError):
            raise FetchError("Invalid response; previous data retained") from None
        time.sleep(1 + attempt)
    raise FetchError("Fetch failed")


def require_list(value):
    if not isinstance(value, list):
        raise FetchError("Expected a list; previous data retained")
    return value


def positive_int(value):
    number = int(value)
    if number < 0:
        raise ValueError("Negative count")
    return number


def image_url(value):
    url = urllib.parse.urlsplit(value or "")
    # Public album art only. Never export provider/account URLs arbitrarily.
    if url.scheme == "https" and not url.username and url.hostname in ("lastfm-img.freetls.fastly.net", "lastfm.freetls.fastly.net", "lastfm-img2.akamaized.net") and "2a96cbd8b46e442fc41c2b86b821562f" not in url.path:
        return value
    return ""


def lastfm(env, previous, now, max_pages):
    def batch(since, until):
        events = []
        complete = False
        for page in range(1, max_pages + 1):
            reply = fetch("https://ws.audioscrobbler.com/2.0/", {
                "method": "user.getrecenttracks", "user": env["LASTFM_USERNAME"],
                "api_key": env["LASTFM_API_KEY"], "format": "json", "limit": 200,
                "page": page, "from": since, "to": until})
            if "error" in reply:
                raise FetchError("Last.fm rejected the request; check credentials or retry later")
            data = reply["recenttracks"]
            rows = require_list(data["track"])
            for row in rows:
                if row.get("@attr", {}).get("nowplaying") == "true":
                    continue
                occurred = positive_int(row["date"]["uts"])
                artist = row["artist"]["#text"]
                album = row.get("album", {}).get("#text", "")
                title = row["name"]
                if not title or not artist or not since <= occurred <= until:
                    raise FetchError("Invalid Last.fm history range")
                images = row.get("image", [])
                cover = next((image_url(i.get("#text")) for i in reversed(images) if image_url(i.get("#text"))), "")
                events.append(dict(id=stable_id(occurred, artist, title, album), occurred=occurred,
                    item=stable_id(artist, title), title=title, creator=artist, album=album,
                    image=cover, url="https://www.last.fm/music/" + urllib.parse.quote(artist, safe="") + "/_/" + urllib.parse.quote(title, safe="")))
            pages = positive_int(data["@attr"]["totalPages"])
            if page >= pages:
                complete = True
                break
            if not rows:
                raise FetchError("Last.fm pagination ended unexpectedly")
            time.sleep(0.25)
        if not complete and not events:
            raise FetchError("Last.fm backfill made no progress")
        return events, complete

    if previous.get("last_success"):
        recent, complete = batch(max(0, previous["last_success"] - 7 * 86400), now)
        if not complete:
            raise FetchError("Recent Last.fm history exceeds page budget; increase --max-pages")
        cursor = previous.get("backfill_before")
        if cursor is not None:
            older, done = batch(0, cursor)
            recent.extend(older)
            # Include the boundary second again; deduplication makes overlap harmless.
            cursor = None if done else min(e["occurred"] for e in older)
        return recent, {"backfill_before": cursor, "history_complete": cursor is None}
    events, done = batch(0, now)
    cursor = None if done else min(e["occurred"] for e in events)
    return events, {"backfill_before": cursor, "history_complete": done}


def steam(env, previous, now, max_pages):
    reply = fetch("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/", {
        "key": env["STEAM_API_KEY"], "steamid": env["STEAM_ID"],
        "include_appinfo": 1, "include_played_free_games": 1})
    data = reply["response"]
    games = require_list(data.get("games"))
    if not games or positive_int(data["game_count"]) != len(games):
        raise FetchError("Steam library is empty or incomplete; check game-detail visibility")
    normalized = []
    for row in games:
        appid = str(positive_int(row["appid"]))
        normalized.append({"appid": appid, "title": str(row["name"]),
            "minutes": positive_int(row["playtime_forever"]),
            "recent_minutes": positive_int(row.get("playtime_2weeks", 0)),
            "last_played": positive_int(row.get("rtime_last_played", 0)),
            "image": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
            "url": f"https://store.steampowered.com/app/{appid}/"})
    return normalized, {"first_observed": previous.get("first_observed", now)}


def tautulli(env, previous, now, max_pages, media_type="movie"):
    base = urllib.parse.urlsplit(env["TAUTULLI_URL"].rstrip("/"))
    if base.scheme not in ("http", "https") or not base.hostname or base.username or base.query or base.fragment:
        raise FetchError("TAUTULLI_URL must be a base HTTP(S) URL without credentials or query")
    user_id = str(positive_int(env["TAUTULLI_USER_ID"]))
    events = {}
    # Full scan is bounded and transactional; retained history is never deleted.
    for page in range(max_pages):
        params = dict(cmd="get_history", user_id=user_id, media_type=media_type, grouping=0,
            include_activity=0, order_column="date", order_dir="desc", start=page * 100, length=100)
        headers = {}
        if env.get("TAUTULLI_AUTH", "header") == "query":
            params["apikey"] = env["TAUTULLI_API_KEY"]
        else:
            headers["X-Api-Key"] = env["TAUTULLI_API_KEY"]
        reply = fetch(env["TAUTULLI_URL"].rstrip("/") + "/api/v2", params, headers)
        response = reply["response"]
        if response.get("result") != "success":
            raise FetchError("Tautulli rejected the request; check credentials and auth mode")
        data = response["data"]
        rows = require_list(data["data"])
        for row in rows:
            # Check the server applied the filter before accepting any history.
            if str(row["user_id"]) != user_id or row["media_type"] != media_type:
                raise FetchError("Tautulli returned another user's history or media type")
            if positive_int(row["stopped"]) == 0 or float(row.get("percent_complete", 0)) < 85:
                continue
            occurred = positive_int(row["stopped"])
            if occurred > now:
                continue
            # Collapse split/resumed playback records by reference_id when available.
            event_id = str(row.get("reference_id") or row["row_id"])
            show = media_type == "episode"
            title = row["grandparent_title"] if show else row["title"]
            event = dict(id=event_id, occurred=occurred,
                item=stable_id("show", title) if show else stable_id(title, str(row.get("year", ""))), title=title,
                creator="TV series" if show else str(row.get("year", "")), image="", url="", rating=None,
                poster_key=str(row.get("grandparent_rating_key" if show else "rating_key", "")))
            if event_id not in events or occurred > events[event_id]["occurred"]:
                events[event_id] = event
        total = positive_int(data["recordsFiltered"])
        if (page + 1) * 100 >= total:
            return list(events.values()), {"history_complete": True}
        if not rows:
            raise FetchError("Tautulli pagination ended unexpectedly")
        time.sleep(0.15)
    raise FetchError("Tautulli history exceeds page budget; increase --max-pages")


def tautulli_tv(env, previous, now, max_pages):
    return tautulli(env, previous, now, max_pages, media_type="episode")


LB = {"lb": "https://letterboxd.com", "tmdb": "https://themoviedb.org"}


def film_link(value):
    parts = urllib.parse.urlsplit(value or "")
    if parts.scheme == "https" and parts.hostname == "letterboxd.com":
        match = re.search(r"/film/([a-z0-9-]+)/", parts.path)
        if match:
            return "https://letterboxd.com/film/" + match[1] + "/"
    return ""


def film_image(description):
    from html.parser import HTMLParser
    class Images(HTMLParser):
        image = ""
        def handle_starttag(self, tag, attrs):
            if tag != "img":
                return
            value = dict(attrs).get("src", "")
            parts = urllib.parse.urlsplit(value)
            if parts.scheme == "https" and parts.hostname in ("a.ltrbxd.com", "resizing.flixster.com"):
                self.image = value
    parser = Images()
    parser.feed(description or "")
    return parser.image


def watched_timestamp(text, tz):
    return int(datetime.strptime(text, "%Y-%m-%d").replace(hour=12, tzinfo=ZoneInfo(tz)).timestamp())


def letterboxd(env, previous, now, max_pages):
    username = env["LETTERBOXD_USERNAME"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", username):
        raise FetchError("Invalid Letterboxd username")
    root = fetch(f"https://letterboxd.com/{username}/rss/", xml=True)
    if root.tag != "rss" or root.find("channel") is None:
        raise FetchError("Expected Letterboxd RSS")
    events = []
    for row in root.findall("./channel/item"):
        watched = row.findtext("lb:watchedDate", namespaces=LB)
        if not watched:
            continue  # Reviews without a watch date and lists are not viewing events.
        title = row.findtext("lb:filmTitle", namespaces=LB)
        year = row.findtext("lb:filmYear", default="", namespaces=LB)
        if not title:
            raise FetchError("Letterboxd entry has no film title")
        rating = row.findtext("lb:memberRating", namespaces=LB)
        # Same title/day identity lets diary CSV and RSS overlap without double counting.
        events.append(dict(id=stable_id(title, year, watched),
            occurred=watched_timestamp(watched, env.get("INTERESTS_TIMEZONE", "America/New_York")),
            item=stable_id(title, year), title=title, creator=year,
            image=film_image(row.findtext("description")), url=film_link(row.findtext("link")),
            rating=float(rating) if rating else None))
    return events, {"history_complete": previous.get("history_complete", False),
        "imported_diary": previous.get("imported_diary", False)}


def import_diary(path, tz):
    events = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"Name", "Year", "Watched Date"} <= set(reader.fieldnames or []):
            raise ValueError("Expected Letterboxd diary.csv with Name, Year, Watched Date")
        for row in reader:
            if not row["Watched Date"]:
                continue
            title, year, watched = row["Name"], row["Year"], row["Watched Date"]
            events.append(dict(id=stable_id(title, year, watched),
                occurred=watched_timestamp(watched, tz), item=stable_id(title, year),
                title=title, creator=year, image="", url="",
                rating=float(row["Rating"]) if row.get("Rating") else None))
    return events


PROVIDERS = {
    "lastfm": (lastfm, ("LASTFM_API_KEY", "LASTFM_USERNAME")),
    "steam": (steam, ("STEAM_API_KEY", "STEAM_ID")),
    "tautulli": (tautulli, ("TAUTULLI_URL", "TAUTULLI_API_KEY", "TAUTULLI_USER_ID")),
    "tautulli_tv": (tautulli_tv, ("TAUTULLI_URL", "TAUTULLI_API_KEY", "TAUTULLI_USER_ID")),
    "letterboxd": (letterboxd, ("LETTERBOXD_USERNAME",)),
}
