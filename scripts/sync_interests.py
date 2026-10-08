#!/usr/bin/env python3
"""Collect private history and write a sanitized Hugo data snapshot; never deploy."""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import tomllib
from pathlib import Path

from interests.storage import atomic_json, connect, exclusive_lock, get_meta, save_events, set_meta
from interests.sources import PROVIDERS, FetchError, import_diary
from interests.publish import export
from interests.artwork import cache_posters

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    values = {}
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise ValueError("Credentials file must be private: chmod 600 the env file")
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep or not key.replace("_", "").isalnum():
                raise ValueError("Credentials file must contain NAME=value lines")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    # Environment variables override file values, useful for a service secret store.
    for _, keys in PROVIDERS.values():
        for key in keys:
            if key in os.environ:
                values[key] = os.environ[key]
    if "TAUTULLI_AUTH" in os.environ:
        values["TAUTULLI_AUTH"] = os.environ["TAUTULLI_AUTH"]
    return values


def collect(db, source, env, now, max_pages):
    provider, keys = PROVIDERS[source]
    supplied = [bool(env.get(key)) for key in keys]
    if not any(supplied):
        return True  # Unconfigured providers preserve saved history.
    previous = get_meta(db, source, {})
    try:
        if not all(supplied):
            raise FetchError("Configuration incomplete; fill all required fields for this source")
        identifiers = {key: env[key] for key in keys if not key.endswith("API_KEY")}
        identity = hashlib.sha256(json.dumps(identifiers, sort_keys=True).encode()).hexdigest()
        if previous.get("identity") and previous["identity"] != identity:
            raise FetchError("Account changed; use a separate state directory to avoid mixing histories")
        rows, details = provider(env, previous, now, max_pages)
        with db:
            if source == "steam":
                for row in rows:
                    db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)", (now, row["appid"], row["minutes"], json.dumps(row)))
            else:
                save_events(db, source, rows)
            set_meta(db, source, {**previous, **details, "identity": identity,
                "last_success": now, "failed": False})
            db.execute("INSERT INTO runs(source,attempted,ok,reason) VALUES (?,?,1,'')", (source, now))
        print(f"{source}: saved {len(rows)} records")
        return True
    except (FetchError, KeyError, TypeError, ValueError, OverflowError) as exc:
        # Only our own controlled errors are safe to log; library errors can include input.
        reason = str(exc) if isinstance(exc, FetchError) else "Response failed validation; previous data retained"
        with db:
            set_meta(db, source, {**previous, "failed": True})
            db.execute("INSERT INTO runs(source,attempted,ok,reason) VALUES (?,?,0,?)", (source, now, reason))
        print(f"{source}: {reason}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".local/interests.env")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".local/interests")
    parser.add_argument("--output", type=Path, default=ROOT / "data/interests.json")
    parser.add_argument("--source", choices=["all", *PROVIDERS], default="all")
    parser.add_argument("--offline", action="store_true", help="Rebuild public views from saved history and books only")
    parser.add_argument("--max-pages", type=int, default=20, help="Per-source pagination budget; Last.fm backfill resumes next run")
    parser.add_argument("--letterboxd-diary", type=Path, help="Import an extracted Letterboxd diary.csv before collection")
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")
    config = tomllib.loads((ROOT / "data/interests_config.toml").read_text())
    env = read_env(args.env_file)
    env["INTERESTS_TIMEZONE"] = config.get("timezone", "America/New_York")
    for public_dir in (ROOT / "static", ROOT / "public", ROOT / "data"):
        if args.state_dir.resolve().is_relative_to(public_dir.resolve()):
            parser.error("Private history must be outside static/, public/, and data/")
    now = int(time.time())
    failed = False
    with exclusive_lock(args.state_dir):
        db = connect(args.state_dir / "history.sqlite3")
        try:
            # Consistent last-run backup, including pre-import state. Keep dated external backups too.
            backup_path = args.state_dir / "history.previous.sqlite3"
            with sqlite3.connect(backup_path) as backup:
                db.backup(backup)
            os.chmod(backup_path, 0o600)
            if args.letterboxd_diary:
                if not env.get("LETTERBOXD_USERNAME"):
                    parser.error("Set LETTERBOXD_USERNAME before importing a diary to bind it to an account")
                identity = hashlib.sha256(json.dumps({"LETTERBOXD_USERNAME": env["LETTERBOXD_USERNAME"]}, sort_keys=True).encode()).hexdigest()
                previous = get_meta(db, "letterboxd", {})
                if previous.get("identity") and previous["identity"] != identity:
                    parser.error("Letterboxd account changed; use a separate state directory")
                events = import_diary(args.letterboxd_diary, env["INTERESTS_TIMEZONE"])
                with db:
                    save_events(db, "letterboxd", events)
                    set_meta(db, "letterboxd", {**get_meta(db, "letterboxd", {}),
                        "imported_diary": True, "identity": identity, "last_success": now, "failed": False})
                print(f"letterboxd: imported {len(events)} diary records")
            if not args.offline:
                for source in PROVIDERS if args.source == "all" else [args.source]:
                    if not collect(db, source, env, now, args.max_pages):
                        failed = True
            if not args.offline and args.source in ("all", "tautulli") and not get_meta(db, "tautulli", {}).get("failed", True):
                cache_posters(db, ROOT, env)
            atomic_json(args.output, export(db, ROOT, config, now))
        finally:
            db.close()
    print("Public snapshot ready; account identifiers and raw history remain private.")
    return 2 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as error:
        # Avoid traceback/URLs containing secrets. Disk/config failures do not replace public JSON.
        print("Collection/export stopped; public snapshot retained. Check file permissions, configuration, state schema, and disk space.", file=sys.stderr)
        raise SystemExit(1)
