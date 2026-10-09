#!/usr/bin/env python3
"""Cron entry point: collect, build a Git export, and check a local release. Never deploy."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from interests.storage import atomic_json, exclusive_lock
from interests.artwork import referenced_posters, prune_posters
from sync_interests import argument_parser


def export_source(root, destination):
    """Only committed source plus the explicit sanitized data/artwork can enter a release."""
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    archive = subprocess.check_output(["git", "archive", "--format=tar", revision], cwd=root)
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        handle.extractall(destination, filter="data")
    snapshot = root / "data/interests.json"
    shutil.copyfile(snapshot, destination / "data/interests.json")
    # Only image files actually referenced by the public projection, never a private tree.
    view = json.loads(snapshot.read_text())
    public = destination / "static/images/interests"
    selected = referenced_posters(view)
    # A poster in an older commit must not survive a later source/selection change.
    prune_posters(view, destination)
    for name in selected:
        source = (root / "static/images/interests" / name).resolve()
        if not source.is_relative_to((root / "static/images/interests").resolve()):
            raise ValueError("Invalid generated artwork path")
        public.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, public / name)
    return revision


def prepare_public_permissions(destination):
    """The release must be readable by a web worker with a different uid/gid."""
    for entry in destination.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Public release must not contain symlinks")
        entry.chmod(0o755 if entry.is_dir() else 0o644)
    destination.chmod(0o755)


def main():
    # Validate CLI usage before interpreting the collector's exit 2 as a provider outage.
    args = argument_parser().parse_args()
    if args.output.resolve() != (ROOT / "data/interests.json").resolve():
        print("The release runner uses data/interests.json; use sync_interests.py for a custom --output.", file=sys.stderr)
        return 1
    os.umask(0o077)
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    with exclusive_lock(local / "interests-refresh"):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_interests.py"), *sys.argv[1:]], cwd=ROOT)
        if result.returncode not in (0, 2):
            return result.returncode
        with tempfile.TemporaryDirectory(prefix="interests-build-", dir=local) as temp:
            source, destination = Path(temp) / "source", Path(temp) / "site"
            source.mkdir()
            revision = export_source(ROOT, source)
            commands = [
                ["hugo", "--cleanDestinationDir", "--panicOnWarning", "--destination", str(destination), "--cacheDir", str(local / "hugo-cache")],
                [sys.executable, str(source / "scripts/check_site.py"), str(destination)],
            ]
            for command in commands:
                check = subprocess.run(command, cwd=source)
                if check.returncode:
                    return check.returncode
            prepare_public_permissions(destination)
            current, previous = local / "interests-site", local / "interests-site.previous"
            if previous.exists():
                shutil.rmtree(previous)  # Only this runner's previous generated release.
            if current.exists():
                current.rename(previous)
            try:
                destination.rename(current)
            except OSError:
                if previous.exists() and not current.exists():
                    previous.rename(current)
                raise
            atomic_json(local / "interests-site.manifest.json", {
                "source_commit": revision,
                "hugo": subprocess.check_output(["hugo", "version"], text=True).strip(),
                "public_data_sha256": hashlib.sha256((source / "data/interests.json").read_bytes()).hexdigest(),
                "source_failures": result.returncode == 2})
        print("Validated local release: " + str(current))
        if result.returncode == 2:
            print("One or more sources failed; the release includes their saved data.", file=sys.stderr)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
