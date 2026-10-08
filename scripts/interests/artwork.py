"""Optional local movie posters; cover failures never invalidate watch history."""
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from .sources import NoRedirect
from .storage import get_meta, set_meta


def cache_posters(db, root, env, budget=12):
    if not all(env.get(k) for k in ("TAUTULLI_URL", "TAUTULLI_API_KEY", "TAUTULLI_USER_ID")):
        return
    covers = get_meta(db, "covers", {})
    directory = root / "static/images/interests"
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
            directory.mkdir(parents=True, exist_ok=True)
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
