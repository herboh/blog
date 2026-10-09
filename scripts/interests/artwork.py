"""Optional local movie posters; cover failures never invalidate watch history."""
import json
import os
import re
import shutil
import tempfile
import urllib.request
from urllib.parse import urlencode, urlsplit

from .sources import NoRedirect
from .storage import get_meta, set_meta, stable_id


PREFIX = "/images/interests/"


def poster_name(image):
    if image.startswith(PREFIX):
        name = image.removeprefix(PREFIX)
        if not re.fullmatch(r"[0-9a-f]{64}\.(jpg|png|webp)", name):
            raise ValueError("Invalid generated poster path")
        return name
    return None


def public_items(view):
    profile = view.get("profile", {})
    for shelf in [*profile.get("watching", []), *profile.get("shelves", [])]:
        yield from shelf["items"]
        yield from shelf["recent"]
    for section in view.get("sections", []):
        for period in section["periods"]:
            yield from period["items"]
        yield from section.get("rated", [])


def referenced_posters(view):
    return {name for item in public_items(view) if (name := poster_name(item.get("image", "")))}


def copy_poster(source, destination, mode):
    fd, temp = tempfile.mkstemp(dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as outgoing, source.open("rb") as incoming:
            shutil.copyfileobj(incoming, outgoing)
            os.fchmod(outgoing.fileno(), mode)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        os.replace(temp, destination)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def migrate_posters(root, directory):
    """Preserve posters produced by the first collector before pruning public assets."""
    public = root / "static/images/interests"
    for source in public.glob("*.*"):
        if not re.fullmatch(r"[0-9a-f]{64}\.(jpg|png|webp)", source.name):
            continue
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = directory / source.name
        if not destination.exists():
            copy_poster(source, destination, 0o600)


def publish_posters(view, root, directory):
    """Expose only posters in the public projection; the full cache stays private."""
    public = root / "static/images/interests"
    selected = referenced_posters(view)
    for name in selected:
        public.mkdir(parents=True, exist_ok=True)
        copy_poster(directory / name, public / name, 0o644)


def prune_posters(view, root):
    """Remove stale generated assets only after the new snapshot was saved."""
    public = root / "static/images/interests"
    selected = referenced_posters(view)
    # These names are owned by the collector. Leave hand-authored assets alone.
    for old in public.glob("*.*"):
        if re.fullmatch(r"[0-9a-f]{64}\.(jpg|png|webp)", old.name) and old.name not in selected:
            old.unlink()


def cache_posters(db, directory, env, budget=12, source="tautulli"):
    if not all(env.get(k) for k in ("TAUTULLI_URL", "TAUTULLI_API_KEY", "TAUTULLI_USER_ID")):
        return
    covers = get_meta(db, "covers", {})
    # Cover the visible selections first, then gradually fill the private cache.
    seen = set()
    attempted = 0
    events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE source=? ORDER BY occurred DESC", (source,))]
    if source == "tautulli_tv":
        from collections import Counter
        counts = Counter(e["item"] for e in events)
        events = events[:3] + sorted(events, key=lambda e: -counts[e["item"]])
    for event in events:
        item = event["item"]
        key = source + ":" + item
        if item in seen or not event.get("poster_key"):
            continue
        seen.add(item)
        filename = item + ".jpg"
        destination = directory / filename
        if destination.is_file():
            covers[key] = "/images/interests/" + filename
            continue
        if attempted >= budget:
            break
        attempted += 1
        params = dict(cmd="pms_image_proxy", rating_key=event["poster_key"], width=300, height=450, img_format="jpg")
        headers = {"User-Agent": "chanfulmer-interests/1.0"}
        if env.get("TAUTULLI_AUTH", "header") == "query":
            params["apikey"] = env["TAUTULLI_API_KEY"]
        else:
            headers["X-Api-Key"] = env["TAUTULLI_API_KEY"]
        request = urllib.request.Request(env["TAUTULLI_URL"].rstrip("/") + "/api/v2?" + urlencode(params), headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
                raw = response.read(2_000_001)
            if not raw.startswith(b"\xff\xd8\xff") or len(raw) > 2_000_000:
                continue
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temp = tempfile.mkstemp(dir=directory)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                os.replace(temp, destination)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            covers[key] = "/images/interests/" + filename
        except (OSError, ValueError):
            continue  # A poster outage must not become a data outage.
    with db:
        set_meta(db, "covers", covers)


def cache_public_art(view, directory, online=True, budget=60):
    """Only credential-free provider CDNs; no image request is made by the visitor."""
    hosts = {"lastfm-img.freetls.fastly.net", "lastfm.freetls.fastly.net", "lastfm-img2.akamaized.net",
             "a.ltrbxd.com", "resizing.flixster.com", "shared.fastly.steamstatic.com", "static.tvmaze.com"}
    remaining = budget
    unavailable = set()
    for item in public_items(view):
        value = item.get("image", "")
        parts = urlsplit(value)
        if parts.scheme != "https" or parts.hostname not in hosts or parts.username:
            continue
        key = stable_id(value)
        saved = next((p for ext in ("jpg", "png", "webp") if (p := directory / (key + "." + ext)).is_file()), None)
        if saved:
            item["image"] = PREFIX + saved.name
            continue
        if not online or remaining <= 0 or value in unavailable:
            # Omit unavailable remote art instead of making the public site depend on it.
            item["image"] = ""
            continue
        remaining -= 1
        unavailable.add(value)
        try:
            request = urllib.request.Request(value, headers={"User-Agent": "chanfulmer-interests/1.0"})
            with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
                raw = response.read(3_000_001)
            ext = "jpg" if raw.startswith(b"\xff\xd8\xff") else "png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None
            if not ext or len(raw) > 3_000_000:
                raise ValueError("Unsupported image")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temp = tempfile.mkstemp(dir=directory)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                saved = directory / (key + "." + ext)
                os.replace(temp, saved)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            item["image"] = PREFIX + saved.name
        except (OSError, ValueError):
            item["image"] = ""
