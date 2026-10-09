"""Optional local movie posters; cover failures never invalidate watch history."""
import json
import os
import re
import shutil
import tempfile
import urllib.request
from urllib.parse import urlencode

from .sources import NoRedirect
from .storage import get_meta, set_meta


PREFIX = "/images/interests/"


def poster_name(image):
    if image.startswith(PREFIX):
        name = image.removeprefix(PREFIX)
        if not re.fullmatch(r"[0-9a-f]{64}\.jpg", name):
            raise ValueError("Invalid generated poster path")
        return name
    return None


def referenced_posters(view):
    names = set()
    for section in view["sections"]:
        items = [item for period in section["periods"] for item in period["items"]]
        items.extend(section.get("rated", []))
        for item in items:
            name = poster_name(item.get("image", ""))
            if name:
                names.add(name)
    return names


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
    for source in public.glob("*.jpg"):
        if not re.fullmatch(r"[0-9a-f]{64}\.jpg", source.name):
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
    for old in public.glob("*.jpg"):
        if re.fullmatch(r"[0-9a-f]{64}\.jpg", old.name) and old.name not in selected:
            old.unlink()


def cache_posters(db, directory, env, budget=12):
    if not all(env.get(k) for k in ("TAUTULLI_URL", "TAUTULLI_API_KEY", "TAUTULLI_USER_ID")):
        return
    covers = get_meta(db, "covers", {})
    # Newest films first. The cache fills gradually without delaying a large backfill.
    seen = set()
    attempted = 0
    for record in db.execute("SELECT payload FROM events WHERE source='tautulli' ORDER BY occurred DESC"):
        event = json.loads(record[0])
        item = event["item"]
        key = "tautulli:" + item
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
