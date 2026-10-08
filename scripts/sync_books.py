#!/usr/bin/env python3

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOOKS_FILE = ROOT / "data" / "books.toml"
CACHE_FILE = ROOT / "data" / "books_cache.json"
COVERS_DIR = ROOT / "static" / "images" / "books"
USER_AGENT = "blog-books-sync/1.0"
TIMEOUT_SECONDS = 20
HARDCOVER_GRAPHQL_URL = "https://api.hardcover.app/v1/graphql"
HARDCOVER_TOKEN_ENV_VARS = ("HARDCOVER_TOKEN", "HARDCOVER_API_TOKEN")
KNOWN_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
CONTENT_TYPE_EXTENSIONS = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "book"


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def clean_isbn(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^0-9xX]", "", str(value))


def book_key(book: dict[str, Any]) -> str:
    custom_id = str(book.get("id") or "").strip()
    if custom_id:
        return slugify(custom_id)

    isbn = clean_isbn(book.get("isbn"))
    if isbn:
        return f"isbn-{isbn.lower()}"

    title = str(book.get("title") or "").strip()
    author = str(book.get("author") or "").strip()
    return slugify(f"{title}-{author}")


def load_books() -> list[dict[str, Any]]:
    with BOOKS_FILE.open("rb") as handle:
        payload = tomllib.load(handle)

    books = payload.get("books")
    if not isinstance(books, list):
        raise ValueError(f"{BOOKS_FILE} is missing a top-level [[books]] list")
    return books


def load_existing_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {"books": {}}

    with CACHE_FILE.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    books = payload.get("books")
    if not isinstance(books, dict):
        return {"books": {}}
    return payload


def request(url: str, *, accept: str = "*/*") -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
        },
    )


def hardcover_token() -> str:
    for name in HARDCOVER_TOKEN_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            if value.lower().startswith("bearer "):
                return value
            return f"Bearer {value}"
    return ""


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(request(url, accept="application/json"), timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_hardcover_json(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    token = hardcover_token()
    if not token:
        raise RuntimeError("HARDCOVER_TOKEN is not set")

    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        HARDCOVER_GRAPHQL_URL,
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "authorization": token,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        data = json.load(response)

    errors = data.get("errors") or []
    if errors:
        messages = ", ".join(error.get("message", "unknown GraphQL error") for error in errors if isinstance(error, dict))
        raise RuntimeError(messages or "Hardcover GraphQL request failed")

    payload_data = data.get("data")
    if not isinstance(payload_data, dict):
        raise RuntimeError("Hardcover response did not include a data object")
    return payload_data


def guess_extension(final_url: str, content_type: str | None) -> str:
    if content_type:
        content_type = content_type.split(";", 1)[0].strip().lower()
        if content_type in CONTENT_TYPE_EXTENSIONS:
            return CONTENT_TYPE_EXTENSIONS[content_type]

    parsed = urllib.parse.urlparse(final_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in KNOWN_EXTENSIONS:
        return suffix

    return ".jpg"


def download_asset(url: str) -> tuple[bytes, str]:
    with urllib.request.urlopen(request(url), timeout=TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type")
        final_url = response.geturl()
        return response.read(), guess_extension(final_url, content_type)


def find_existing_cover(book_id: str) -> Path | None:
    for extension in KNOWN_EXTENSIONS:
        candidate = COVERS_DIR / f"{book_id}{extension}"
        if candidate.exists():
            return candidate
    return None


def delete_existing_covers(book_id: str) -> None:
    for extension in KNOWN_EXTENSIONS:
        candidate = COVERS_DIR / f"{book_id}{extension}"
        if candidate.exists():
            candidate.unlink()


def normalize_book_metadata(title: str | None, authors: list[str], published: str | None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if title:
        metadata["title"] = title
    if authors:
        metadata["author"] = ", ".join(author for author in authors if author)
    if published:
        metadata["published"] = published
    return metadata


def parse_year(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\d{4}", text)
    if match:
        return match.group(0)
    return text


def merge_metadata(record: dict[str, Any], metadata: dict[str, str], book: dict[str, Any]) -> None:
    for field, value in metadata.items():
        if field == "title" and str(book.get("title") or "").strip():
            continue
        if field == "author" and str(book.get("author") or "").strip():
            continue
        record[field] = value


def hardcover_search(book: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    isbn = clean_isbn(book.get("isbn"))
    title = str(book.get("title") or "").strip()
    author = str(book.get("author") or "").strip()
    explicit_id = book.get("hardcover_id")
    if explicit_id not in (None, ""):
        return {"id": int(explicit_id)}, []

    query_text = isbn or " ".join(part for part in (title, author) if part).strip()
    if not query_text:
        return {}, []

    query = """
    query SearchHardcoverBooks($query: String!, $perPage: Int!) {
      search(query: $query, query_type: "Book", per_page: $perPage, page: 1) {
        ids
        results
      }
    }
    """
    data = fetch_hardcover_json(query, {"query": query_text, "perPage": 10})
    search = data.get("search") or {}
    ids = search.get("ids") or []
    results = search.get("results") or []

    candidates: list[dict[str, Any]] = []
    for index, raw in enumerate(results):
        candidate = raw
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        if not isinstance(candidate, dict):
            continue
        entry = dict(candidate)
        if index < len(ids):
            entry["id"] = ids[index]
        candidates.append(entry)

    normalized_title = normalize_text(title)
    normalized_author = normalize_text(author)

    def score(candidate: dict[str, Any]) -> float:
        value = 0.0
        candidate_title = normalize_text(str(candidate.get("title") or ""))
        candidate_authors = [normalize_text(str(name)) for name in candidate.get("author_names") or []]
        candidate_isbns = [clean_isbn(item) for item in candidate.get("isbns") or []]

        if isbn and isbn in candidate_isbns:
            value += 200
        if candidate_title == normalized_title and normalized_title:
            value += 120
        elif normalized_title and normalized_title in candidate_title:
            value += 80
        value += difflib.SequenceMatcher(None, normalized_title, candidate_title).ratio() * 35
        if normalized_author and normalized_author in candidate_authors:
            value += 35
        try:
            value += min(float(candidate.get("users_count") or 0) / 2000.0, 5.0)
        except (TypeError, ValueError):
            pass
        return value

    best = max(candidates, key=score) if candidates else {}
    return best, candidates


def hardcover_book_details(book_id_value: int) -> tuple[dict[str, str], str | None, dict[str, Any]]:
    query = """
    query HardcoverBookDetails($bookId: Int!) {
      books(where: {id: {_eq: $bookId}}, limit: 1) {
        id
        title
        release_year
        slug
        author_names
        image {
          url
        }
        default_cover_edition {
          id
          isbn_13
          release_year
          edition_format
          image {
            url
          }
        }
      }
    }
    """
    data = fetch_hardcover_json(query, {"bookId": int(book_id_value)})
    books = data.get("books") or []
    if not books:
        return {}, None, {}

    record = books[0]
    metadata = normalize_book_metadata(
        record.get("title"),
        record.get("author_names") or [],
        parse_year(record.get("release_year")),
    )
    edition = record.get("default_cover_edition") or {}
    image = record.get("image") or {}
    edition_image = edition.get("image") or {}
    cover_url = str(edition_image.get("url") or image.get("url") or "").strip() or None
    extra = {
        "hardcover_id": record.get("id"),
        "hardcover_slug": record.get("slug"),
        "edition_isbn": edition.get("isbn_13"),
        "edition_format": edition.get("edition_format"),
    }
    return metadata, cover_url, extra


def hardcover_lookup(book: dict[str, Any]) -> tuple[dict[str, str], str | None, dict[str, Any]]:
    best, _ = hardcover_search(book)
    if not best:
        return {}, None, {}

    try:
        book_id_value = int(best.get("id"))
    except (TypeError, ValueError):
        return {}, None, {}

    return hardcover_book_details(book_id_value)


def open_library_lookup(book: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    isbn = clean_isbn(book.get("isbn"))
    if not isbn:
        return {}, None

    url = (
        "https://openlibrary.org/api/books?"
        + urllib.parse.urlencode(
            {
                "bibkeys": f"ISBN:{isbn}",
                "format": "json",
                "jscmd": "data",
            }
        )
    )
    payload = fetch_json(url)
    record = payload.get(f"ISBN:{isbn}") or {}

    title = record.get("title")
    authors = [author.get("name", "") for author in record.get("authors", []) if isinstance(author, dict)]
    published = record.get("publish_date")
    metadata = normalize_book_metadata(title, authors, published)

    cover = record.get("cover") or {}
    for size in ("large", "medium", "small"):
        cover_url = cover.get(size)
        if cover_url:
            return metadata, str(cover_url)

    return metadata, f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"


def open_library_search(book: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    title = str(book.get("title") or "").strip()
    author = str(book.get("author") or "").strip()
    if not title:
        return {}, None

    params = {
        "title": title,
        "limit": 10,
    }
    if author:
        params["author"] = author

    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
    payload = fetch_json(url)
    docs = payload.get("docs") or []
    if not docs:
        return {}, None

    normalized_title = normalize_text(title)
    normalized_author = normalize_text(author)

    def score(candidate: dict[str, Any]) -> float:
        candidate_title = str(candidate.get("title") or candidate.get("title_suggest") or "").strip()
        candidate_author_names = candidate.get("author_name") or []
        candidate_title_normalized = normalize_text(candidate_title)
        candidate_authors_normalized = [normalize_text(name) for name in candidate_author_names]

        value = 0.0
        if candidate_title_normalized == normalized_title:
            value += 100
        elif normalized_title and normalized_title in candidate_title_normalized:
            value += 70
        value += difflib.SequenceMatcher(None, normalized_title, candidate_title_normalized).ratio() * 30
        if candidate.get("cover_i"):
            value += 10
        if normalized_author and normalized_author in candidate_authors_normalized:
            value += 15
        return value

    record = max(docs, key=score)

    authors = record.get("author_name") or []
    published = record.get("first_publish_year")
    metadata = normalize_book_metadata(
        record.get("title") or record.get("title_suggest"),
        authors,
        str(published) if published else None,
    )

    cover_id = record.get("cover_i")
    if cover_id:
        return metadata, f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"

    return metadata, None


def resolve_cover_candidates(book: dict[str, Any]) -> tuple[list[tuple[str, str, dict[str, str]]], dict[str, str]]:
    candidates: list[tuple[str, str, dict[str, str]]] = []
    fallback_metadata: dict[str, str] = {}

    if hardcover_token():
        try:
            hardcover_metadata, hardcover_cover, hardcover_extra = hardcover_lookup(book)
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
            hardcover_metadata, hardcover_cover, hardcover_extra = {}, None, {}
            print(f"[warn] {book_key(book)}: hardcover lookup failed: {exc}", file=sys.stderr)
        if hardcover_metadata:
            fallback_metadata.update(hardcover_metadata)
        if hardcover_cover:
            candidates.append(("hardcover", hardcover_cover, hardcover_metadata))
        if hardcover_extra:
            for key, value in hardcover_extra.items():
                if value not in (None, ""):
                    fallback_metadata[key] = str(value)

    cover_source = str(book.get("cover_source") or "").strip()
    if cover_source:
        candidates.append(("manual", cover_source, {}))

    try:
        open_library_metadata, open_library_cover = open_library_lookup(book)
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        open_library_metadata, open_library_cover = {}, None
        print(f"[warn] {book_key(book)}: open library lookup failed: {exc}", file=sys.stderr)
    if open_library_metadata:
        fallback_metadata.update(open_library_metadata)
    if open_library_cover:
        candidates.append(("openlibrary", open_library_cover, open_library_metadata))

    try:
        search_metadata, search_cover = open_library_search(book)
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        search_metadata, search_cover = {}, None
        print(f"[warn] {book_key(book)}: open library search failed: {exc}", file=sys.stderr)
    if search_metadata and not fallback_metadata:
        fallback_metadata.update(search_metadata)
    if search_cover:
        candidates.append(("openlibrary-search", search_cover, search_metadata))

    return candidates, fallback_metadata


def local_path_to_public_url(path: Path) -> str:
    relative = path.relative_to(ROOT / "static")
    return "/" + relative.as_posix()


def resolve_manual_cover_file(book: dict[str, Any]) -> str | None:
    cover_file = str(book.get("cover_file") or "").strip()
    if not cover_file:
        return None

    relative_path = cover_file.lstrip("/")
    local_file = ROOT / "static" / relative_path
    if local_file.exists():
        return cover_file if cover_file.startswith("/") else f"/{relative_path}"
    return None


def sync_book(
    book: dict[str, Any],
    cached_record: dict[str, Any],
    *,
    refresh: bool,
) -> tuple[dict[str, Any], str]:
    book_id = book_key(book)
    manual_cover_file = resolve_manual_cover_file(book)
    existing_cover = find_existing_cover(book_id)

    record: dict[str, Any] = {}
    if not str(book.get("title") or "").strip() and cached_record.get("title"):
        record["title"] = cached_record["title"]
    if not str(book.get("author") or "").strip() and cached_record.get("author"):
        record["author"] = cached_record["author"]
    for field in ("published", "hardcover_id", "hardcover_slug", "edition_isbn", "edition_format"):
        if cached_record.get(field):
            record[field] = cached_record[field]
    if manual_cover_file:
        record["cover_image"] = manual_cover_file
        record["cover_source"] = "local"
        return record, "manual"

    if existing_cover and not refresh:
        record["cover_image"] = local_path_to_public_url(existing_cover)
        record.setdefault("cover_source", "local-cache")
        return record, "reused"

    candidates, metadata = resolve_cover_candidates(book)
    if metadata:
        merge_metadata(record, metadata, book)

    if not candidates:
        return record, "missing"

    for provider, cover_url, provider_metadata in candidates:
        if provider_metadata:
            merge_metadata(record, provider_metadata, book)

        try:
            image_bytes, extension = download_asset(cover_url)
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            message = str(exc).strip() or exc.__class__.__name__
            print(f"[warn] {book_id}: failed to download {cover_url}: {message}", file=sys.stderr)
            continue

        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        delete_existing_covers(book_id)
        output_path = COVERS_DIR / f"{book_id}{extension}"
        output_path.write_bytes(image_bytes)
        record["cover_image"] = local_path_to_public_url(output_path)
        record["cover_source"] = provider
        return record, "downloaded"

    return record, "missing"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch local book covers and update Hugo cache data.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download covers even when a local cached cover already exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    books = load_books()
    existing_cache = load_existing_cache()
    existing_records = existing_cache.get("books") or {}

    new_records: dict[str, Any] = {}
    downloaded = 0
    reused = 0
    manual = 0
    missing = 0

    for book in books:
        if not isinstance(book, dict):
            continue

        book_id = book_key(book)
        record, status = sync_book(book, existing_records.get(book_id, {}), refresh=args.refresh)
        if record:
            new_records[book_id] = record

        if status == "downloaded":
            downloaded += 1
        elif status == "reused":
            reused += 1
        elif status == "manual":
            manual += 1
        else:
            missing += 1

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "books": new_records,
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    total = len(books)
    print(
        f"Processed {total} books: {downloaded} downloaded, "
        f"{reused} reused, {manual} manual, {missing} missing"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
