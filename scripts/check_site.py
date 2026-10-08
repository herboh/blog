#!/usr/bin/env python3
"""Check a Hugo build's local links, assets, fragments, and XML, offline."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids = set()
        self.references = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.ids.add(attrs["name"])
        for attribute in ("href", "src", "poster"):
            if attrs.get(attribute):
                self.references.append(attrs[attribute])
        if attrs.get("srcset"):
            self.references.extend(item.strip().split()[0] for item in attrs["srcset"].split(",") if item.strip())


def check(root, base_url):
    pages = {path: Page(path) for path in sorted(root.rglob("*.html"))}
    errors = []
    references = 0
    site = urlsplit(base_url)
    if not (root / "index.html").is_file():
        errors.append("Missing index.html; build the site first")

    for path, page in pages.items():
        relative = path.relative_to(root).as_posix()
        page_url = urljoin(base_url, relative.removesuffix("index.html"))
        for reference in page.references:
            url = urlsplit(urljoin(page_url, reference))
            if url.scheme not in ("http", "https") or url.netloc != site.netloc:
                continue
            references += 1
            target = (root / unquote(url.path).lstrip("/")).resolve()
            if not target.is_relative_to(root):
                errors.append(f"{relative}: path escapes build directory: {reference}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"{relative}: missing target: {reference}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors.append(f"{relative}: missing fragment: {reference}")

    xml_files = sorted(root.rglob("*.xml"))
    for path in xml_files:
        try:
            ET.parse(path)
        except ET.ParseError as error:
            errors.append(f"{path.relative_to(root)}: invalid XML: {error}")

    for error in errors:
        print(error)
    print(f"Checked {len(pages)} HTML pages, {references} local references, {len(xml_files)} XML files; {len(errors)} errors.")
    return bool(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Hugo output directory")
    parser.add_argument("--base-url", default="https://chanfulmer.com/")
    args = parser.parse_args()
    return check(args.directory.resolve(), args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
