#!/usr/bin/env python3
"""
Optimized Wikipedia article processor.
Extracts articles from wikidump, fixes links, and reports image requirements.
"""

from pathlib import Path
import re
import json
import logging
import argparse
import shutil
from typing import Set, List, Dict, Tuple
from dataclasses import dataclass

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **k: x

# Configuration
SOURCE_DIR = Path("/home/chan/code/wiki/gwiki/A/")
SOURCE_IMAGES_DIR = Path("/home/chan/code/wiki/gwiki/I/")
TARGET_DIR = Path("/home/chan/code/git/blog/wiki/A/")
TARGET_IMAGES_DIR = Path("/home/chan/code/git/blog/wiki/I/")
TITLES_FILE = Path("gtitles.txt")
REDIRECT_THRESHOLD = 1000  # bytes
BROKEN_LINK_REPLACEMENT = '<a href="../not_g.html" class="not_g"'


@dataclass
class ArticleResult:
    """Result of processing a single article."""

    name: str
    title: str
    size_bytes: int
    is_redirect: bool
    images: List[str]
    processed: bool
    error: str = ""


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler("wiki_processing.log"),
            logging.StreamHandler(),
        ],
    )


def load_desired_articles(titles_file: Path) -> Set[str]:
    """Load the list of articles we want to process."""
    try:
        content = titles_file.read_text(encoding="utf-8")
        titles = {line.strip() for line in content.splitlines() if line.strip()}
        logging.info(f"Loaded {len(titles)} desired article titles")
        return titles
    except FileNotFoundError:
        logging.error(f"Titles file not found: {titles_file}")
        raise


def is_redirect_file(file_path: Path, threshold: int = REDIRECT_THRESHOLD) -> bool:
    """Quick check if file is likely a redirect based on size."""
    try:
        return file_path.stat().st_size < threshold
    except OSError:
        return True  # Assume redirect if we can't read


def extract_title_from_html(html: str) -> str:
    """Extract title from HTML using regex (faster than BeautifulSoup for this)."""
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_images_from_html(html: str) -> List[str]:
    """Extract image sources using regex."""
    pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
    matches = re.findall(pattern, html, re.IGNORECASE)
    # Clean and deduplicate
    images = []
    seen = set()
    for src in matches:
        # Get just the filename
        filename = Path(src).name
        if filename and filename not in seen:
            images.append(filename)
            seen.add(filename)
    return sorted(images)


def fix_links_fast(html: str, valid_articles: Set[str]) -> str:
    """
    Fix article links using string replacement (faster than BeautifulSoup).
    Keep links to valid articles, mark others as broken.
    """

    def replace_link(match):
        full_tag = match.group(0)
        href_content = match.group(1)

        # Extract the base article name (remove .html and fragments)
        base_name = href_content.split("#")[0]
        if base_name.endswith(".html"):
            base_name = base_name[:-5]

        if not base_name or base_name in valid_articles:
            # Valid link - ensure it has .html extension
            if not href_content.endswith(".html") and "#" not in href_content:
                return full_tag.replace(
                    f'href="{href_content}"', f'href="{href_content}.html"'
                )
            return full_tag
        else:
            # Broken link - replace with broken link markup
            return BROKEN_LINK_REPLACEMENT + full_tag[full_tag.find(" ") :]

    # Pattern to match <a href="..."> tags
    pattern = r'<a\s+href=["\']([^"\']*)["\'][^>]*>'
    return re.sub(pattern, replace_link, html, flags=re.IGNORECASE)


def process_article(file_path: Path, valid_articles: Set[str]) -> ArticleResult:
    """Process a single article file."""
    name = file_path.name

    # Quick redirect check
    if is_redirect_file(file_path):
        return ArticleResult(
            name=name,
            title="",
            size_bytes=file_path.stat().st_size,
            is_redirect=True,
            images=[],
            processed=False,
        )

    try:
        html = file_path.read_text(encoding="utf-8", errors="ignore")
        size_bytes = len(html.encode("utf-8"))

        # Double-check redirect status by content if size is close to threshold
        if size_bytes < REDIRECT_THRESHOLD * 1.2:  # 20% buffer
            # Simple heuristic: redirects typically have very little content
            text_content = re.sub(r"<[^>]+>", "", html).strip()
            if len(text_content) < 200:  # Very little actual text content
                return ArticleResult(
                    name=name,
                    title=extract_title_from_html(html),
                    size_bytes=size_bytes,
                    is_redirect=True,
                    images=[],
                    processed=False,
                )

        title = extract_title_from_html(html)
        if not title:
            return ArticleResult(
                name=name,
                title="",
                size_bytes=size_bytes,
                is_redirect=False,
                images=[],
                processed=False,
                error="No title found",
            )

        # Fix links and extract images
        fixed_html = fix_links_fast(html, valid_articles)
        images = extract_images_from_html(html)

        # Write processed file
        TARGET_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TARGET_DIR / f"{name}.html"
        output_path.write_text(fixed_html, encoding="utf-8")

        return ArticleResult(
            name=name,
            title=title,
            size_bytes=size_bytes,
            is_redirect=False,
            images=images,
            processed=True,
        )

    except Exception as e:
        return ArticleResult(
            name=name,
            title="",
            size_bytes=0,
            is_redirect=False,
            images=[],
            processed=False,
            error=str(e),
        )


def copy_images(all_images: Set[str]) -> int:
    """Copy required images from source to target."""
    TARGET_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0

    for img_name in tqdm(all_images, desc="Copying images", unit="img"):
        src_path = SOURCE_IMAGES_DIR / img_name
        dst_path = TARGET_IMAGES_DIR / img_name

        if src_path.exists() and not dst_path.exists():
            try:
                shutil.copy2(src_path, dst_path)
                copied += 1
            except Exception as e:
                logging.warning(f"Failed to copy {img_name}: {e}")

    return copied


def main():
    parser = argparse.ArgumentParser(
        description="Process Wikipedia articles efficiently"
    )
    parser.add_argument(
        "--titles",
        type=Path,
        default=TITLES_FILE,
        help="File containing desired article titles",
    )
    parser.add_argument(
        "--copy-images",
        action="store_true",
        help="Copy required images to target directory",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default="processing_results.json",
        help="Output file for processing results",
    )

    args = parser.parse_args()
    setup_logging()

    # Load desired articles
    desired_articles = load_desired_articles(args.titles)

    # Find existing files that match our desired articles
    existing_files = {
        p.name: p
        for p in SOURCE_DIR.iterdir()
        if p.is_file() and p.name in desired_articles
    }

    found_count = len(existing_files)
    missing_count = len(desired_articles) - found_count

    logging.info(
        f"Found {found_count} articles, {missing_count} missing from desired list"
    )

    if missing_count > 0:
        missing = desired_articles - set(existing_files.keys())
        logging.warning(
            f"Missing articles: {sorted(list(missing))[:10]}..."
        )  # Show first 10

    # Process articles
    results = []
    all_images = set()
    processed_count = 0
    redirect_count = 0
    error_count = 0

    logging.info(f"Processing {found_count} articles...")

    for file_path in tqdm(existing_files.values(), desc="Processing", unit="article"):
        result = process_article(file_path, desired_articles)
        results.append(result)

        if result.is_redirect:
            redirect_count += 1
        elif result.processed:
            processed_count += 1
            all_images.update(result.images)
        else:
            error_count += 1

    # Copy images if requested
    if args.copy_images and all_images:
        copied = copy_images(all_images)
        logging.info(f"Copied {copied}/{len(all_images)} images")

    # Generate output summary
    summary = {
        "total_desired": len(desired_articles),
        "found_files": found_count,
        "processed": processed_count,
        "redirects": redirect_count,
        "errors": error_count,
        "total_images": len(all_images),
        "articles": [
            {
                "name": r.name,
                "title": r.title,
                "size_bytes": r.size_bytes,
                "is_redirect": r.is_redirect,
                "processed": r.processed,
                "images": r.images,
                "image_count": len(r.images),
                "error": r.error,
            }
            for r in results
        ],
    }

    # Save results
    args.output_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logging.info(f"""
Processing complete:
  • {processed_count} articles processed successfully
  • {redirect_count} redirects skipped  
  • {error_count} errors encountered
  • {len(all_images)} unique images referenced
  • Results saved to {args.output_json}
""")


if __name__ == "__main__":
    main()
