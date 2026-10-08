"""Offline contract tests for retention, history arithmetic and publication boundaries."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from interests import publish, sources
from interests.storage import atomic_json, connect, get_meta, save_events, set_meta
from sync_interests import collect, read_env

NOW = 1791450000


def track(title="Track", artist="Artist", occurred=NOW - 100):
    return dict(id=str(occurred) + title, item=title, occurred=occurred, title=title,
                creator=artist, album="Album", image="", url="https://www.last.fm/music/Artist/_/Track")


def game(app="10", minutes=100, recent=10):
    return dict(appid=app, minutes=minutes, recent_minutes=recent, last_played=NOW,
                title="Example Game", url=f"https://store.steampowered.com/app/{app}/", image="")


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = connect(Path(self.temp.name) / "history.sqlite3")
        self.addCleanup(self.db.close)

    def snapshot(self, at, games):
        for g in games:
            self.db.execute("INSERT INTO snapshots VALUES (?,?,?,?)", (at, g["appid"], g["minutes"], json.dumps(g)))
        self.db.commit()

    def test_failure_retains_history_and_last_success_then_recovers(self):
        env = {"LASTFM_API_KEY": "SECRET-DO-NOT-PUBLISH", "LASTFM_USERNAME": "PRIVATE-ACCOUNT"}
        with patch.dict(sources.PROVIDERS, {"lastfm": (lambda *a: ([track()], {"history_complete": True}), sources.PROVIDERS["lastfm"][1])}):
            self.assertTrue(collect(self.db, "lastfm", env, NOW, 2))
        with patch.dict(sources.PROVIDERS, {"lastfm": (lambda *a: (_ for _ in ()).throw(sources.FetchError("HTTP 503")), sources.PROVIDERS["lastfm"][1])}):
            self.assertFalse(collect(self.db, "lastfm", env, NOW + 60, 2))
        self.assertEqual(get_meta(self.db, "lastfm")["last_success"], NOW)
        section = publish.event_section(self.db, "lastfm", "music", "Listening", NOW + 60, ZoneInfo("UTC"))
        self.assertEqual(section["status"], "saved")
        self.assertEqual(section["periods"][0]["metrics"][0]["value"], "1")
        data = json.dumps(publish.export(self.db, ROOT, {}, NOW + 60))
        for forbidden in ("SECRET-DO-NOT-PUBLISH", "PRIVATE-ACCOUNT", "identity", "user_id", "apikey"):
            self.assertNotIn(forbidden, data)
        # Redundant successful fetches must not double count.
        with patch.dict(sources.PROVIDERS, {"lastfm": (lambda *a: ([track()], {"history_complete": True}), sources.PROVIDERS["lastfm"][1])}):
            self.assertTrue(collect(self.db, "lastfm", env, NOW + 120, 2))
        self.assertEqual(self.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
        self.assertFalse(get_meta(self.db, "lastfm")["failed"])

    def test_identity_change_rejected_without_calling_provider(self):
        with self.db:
            set_meta(self.db, "lastfm", {"identity": "another-account", "last_success": NOW})
        with patch("interests.sources.fetch") as request:
            self.assertFalse(collect(self.db, "lastfm", {"LASTFM_USERNAME": "new", "LASTFM_API_KEY": "secret"}, NOW, 2))
            request.assert_not_called()

    def test_steam_baseline_deltas_corrections_and_filters(self):
        self.snapshot(NOW - 86400, [game(minutes=1000), game("20", 200)])
        self.snapshot(NOW, [game(minutes=1060), game("20", 290)])
        self.snapshot(NOW + 60, [game(minutes=900), game("20", 300)])
        self.snapshot(NOW + 120, [game(minutes=930), game("20", 320)])
        with self.db:
            set_meta(self.db, "steam", {"last_success": NOW + 120, "first_observed": NOW - 86400})
        section = publish.steam_section(self.db, {"exclude_steam_apps": [20]}, NOW + 120, ZoneInfo("UTC"))
        annual = section["periods"][2]
        self.assertEqual(annual["metrics"][0]["value"], "1.5")  # 60 + 30, no initial 1000 or correction.
        self.assertEqual(section["periods"][1]["metrics"][0]["value"], "15.5")
        self.assertNotIn("/app/20", json.dumps(section))
        self.assertIn("corrections", section["coverage"])

    def test_new_steam_game_does_not_backdate_lifetime(self):
        self.snapshot(NOW - 100, [game()])
        self.snapshot(NOW, [game(minutes=110), game("30", minutes=9000)])
        section = publish.steam_section(self.db, {}, NOW, ZoneInfo("UTC"))
        self.assertEqual(section["periods"][2]["metrics"][0]["value"], "0.2")

    def test_movies_choose_one_source(self):
        with self.db:
            save_events(self.db, "tautulli", [track("Film")])
            save_events(self.db, "letterboxd", [track("Film")])
            set_meta(self.db, "tautulli", {"last_success": NOW})
            set_meta(self.db, "letterboxd", {"last_success": NOW})
        movies = publish.export(self.db, ROOT, {}, NOW)["sections"][3]
        self.assertEqual(movies["source"], "Plex · Tautulli")
        self.assertEqual(movies["periods"][1]["metrics"][0]["value"], "1")

    def test_cross_year_events_use_configured_timezone(self):
        from datetime import datetime, timezone
        occurred = int(datetime(2026, 1, 1, 2, tzinfo=timezone.utc).timestamp())
        with self.db:
            save_events(self.db, "lastfm", [track(occurred=occurred)])
        periods = publish.event_section(self.db, "lastfm", "music", "Listening", NOW, ZoneInfo("America/New_York"))["periods"]
        self.assertEqual(periods[-1]["id"], "2025")

    def test_invalid_payload_does_not_replace_snapshot(self):
        with self.db:
            set_meta(self.db, "steam", {"last_success": NOW - 60})
        with patch("interests.sources.fetch", return_value={"response": {"game_count": 0}}):
            self.assertFalse(collect(self.db, "steam", {"STEAM_ID": "123", "STEAM_API_KEY": "secret"}, NOW, 2))
        self.assertEqual(get_meta(self.db, "steam")["last_success"], NOW - 60)

    def test_failed_source_recent_period_stays_at_successful_sync(self):
        with self.db:
            save_events(self.db, "lastfm", [track()])
            set_meta(self.db, "lastfm", {"last_success": NOW, "failed": True})
        view = publish.event_section(self.db, "lastfm", "music", "Listening", NOW + 90 * 86400, ZoneInfo("UTC"))
        self.assertEqual(view["periods"][0]["metrics"][0]["value"], "1")

    def test_missing_cached_poster_is_not_exported(self):
        with self.db:
            save_events(self.db, "tautulli", [track("Film")])
            set_meta(self.db, "tautulli", {"last_success": NOW})
            set_meta(self.db, "covers", {"tautulli:Film": "/images/interests/missing.jpg"})
        view = publish.export(self.db, ROOT, {}, NOW)
        self.assertEqual(view["sections"][3]["periods"][0]["items"][0]["image"], "")

    def test_transaction_rolls_back_malformed_batch(self):
        env = {"LASTFM_API_KEY": "secret", "LASTFM_USERNAME": "person"}
        def bad(*args):
            return [track(), {"id": "bad"}], {}
        with patch.dict(sources.PROVIDERS, {"lastfm": (bad, sources.PROVIDERS["lastfm"][1])}):
            self.assertFalse(collect(self.db, "lastfm", env, NOW, 2))
        self.assertEqual(self.db.execute("SELECT count(*) FROM events").fetchone()[0], 0)


class ProviderTest(unittest.TestCase):
    def test_lastfm_nowplaying_skipped_and_backfill_resumes(self):
        row = {"name": "Track", "artist": {"#text": "Artist"}, "album": {"#text": "Album"}, "date": {"uts": str(NOW - 10)}}
        data = {"recenttracks": {"track": [{"@attr": {"nowplaying": "true"}}, row], "@attr": {"totalPages": "5"}}}
        with patch("interests.sources.fetch", return_value=data), patch("interests.sources.time.sleep"):
            events, meta = sources.lastfm({"LASTFM_API_KEY": "key", "LASTFM_USERNAME": "person"}, {}, NOW, 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(meta["backfill_before"], NOW - 10)
        self.assertFalse(meta["history_complete"])

    def test_lastfm_tail_overflow_is_failure_not_a_silent_gap(self):
        row = {"name": "Track", "artist": {"#text": "Artist"}, "date": {"uts": str(NOW - 10)}}
        data = {"recenttracks": {"track": [row], "@attr": {"totalPages": "9"}}}
        with patch("interests.sources.fetch", return_value=data), patch("interests.sources.time.sleep"):
            with self.assertRaises(sources.FetchError):
                sources.lastfm({"LASTFM_API_KEY": "key", "LASTFM_USERNAME": "person"}, {"last_success": NOW - 50}, NOW, 1)

    def test_tautulli_requires_exact_user_filter(self):
        row = dict(user_id=99, media_type="movie")
        response = {"response": {"result": "success", "data": {"data": [row], "recordsFiltered": 1}}}
        env = dict(TAUTULLI_URL="http://localhost:8181", TAUTULLI_USER_ID="12", TAUTULLI_API_KEY="secret")
        with patch("interests.sources.fetch", return_value=response) as fetch:
            with self.assertRaises(sources.FetchError):
                sources.tautulli(env, {}, NOW, 2)
            self.assertEqual(fetch.call_args.args[1]["user_id"], "12")
            self.assertEqual(fetch.call_args.args[2], {"X-Api-Key": "secret"})

    def test_tautulli_skips_incomplete_and_groups_resume(self):
        common = dict(user_id=12, media_type="movie", stopped=NOW, started=NOW - 300,
                      reference_id=1, title="Film", year=2020)
        rows = [{**common, "row_id": 1, "percent_complete": 30}, {**common, "row_id": 2, "percent_complete": 95}]
        reply = {"response": {"result": "success", "data": {"data": rows, "recordsFiltered": 2}}}
        with patch("interests.sources.fetch", return_value=reply):
            events, _ = sources.tautulli(dict(TAUTULLI_URL="http://localhost:8181", TAUTULLI_USER_ID="12", TAUTULLI_API_KEY="secret"), {}, NOW, 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], "1")

    def test_letterboxd_csv_and_feed_deduplicate_and_strip_profile_links(self):
        import xml.etree.ElementTree as ET
        feed = ET.fromstring('''<rss xmlns:letterboxd="https://letterboxd.com"><channel><item>
        <link>https://letterboxd.com/PRIVATE/film/film/</link><guid>private-link</guid>
        <letterboxd:filmTitle>Film</letterboxd:filmTitle><letterboxd:filmYear>2020</letterboxd:filmYear>
        <letterboxd:watchedDate>2026-10-01</letterboxd:watchedDate><letterboxd:memberRating>4.5</letterboxd:memberRating>
        </item><item><title>A list is not a watch</title></item></channel></rss>''')
        with patch("interests.sources.fetch", return_value=feed):
            events, _ = sources.letterboxd({"LETTERBOXD_USERNAME": "PRIVATE"}, {}, NOW, 1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "diary.csv"
            path.write_text('Name,Year,Watched Date,Rating\nFilm,2020,2026-10-01,4.5\n')
            imported = sources.import_diary(path, "America/New_York")
        self.assertEqual(events[0]["id"], imported[0]["id"])
        self.assertEqual(events[0]["url"], "https://letterboxd.com/film/film/")
        self.assertNotIn("PRIVATE", json.dumps(events))

    def test_atomic_output_failure_retains_old_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "public.json"
            atomic_json(path, {"old": True})
            before = path.read_bytes()
            with patch("interests.storage.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    atomic_json(path, {"new": True})
            self.assertEqual(path.read_bytes(), before)

    def test_credentials_permissions_and_no_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keys.env"
            path.write_text("LASTFM_API_KEY='$(do-not-run)'\nLASTFM_USERNAME=person\n")
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_env(path)
            path.chmod(0o600)
            self.assertEqual(read_env(path)["LASTFM_API_KEY"], "$(do-not-run)")


class ReleaseTest(unittest.TestCase):
    def test_release_exports_git_source_not_untracked_private_files(self):
        from refresh_interests import export_source
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            revision = export_source(ROOT, target)
            self.assertEqual(len(revision), 40)
            self.assertTrue((target / "layouts/interests/interests.html").is_file())
            self.assertFalse((target / ".local").exists())
            self.assertFalse((target / "content/blog/diy-sonos.md").exists())
            self.assertEqual((target / "data/interests.json").read_bytes(), (ROOT / "data/interests.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
