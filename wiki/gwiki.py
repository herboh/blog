from pathlib import Path
from bs4 import BeautifulSoup
from textwrap import shorten
import json, logging, argparse, re, sys, shutil

try:
    from tqdm import tqdm  # optional nice progress bar
except ImportError:
    tqdm = lambda x, **k: x  # fallback: plain iterator

# Source directory containing the raw Wikipedia articles (files named like "Galaxy", "Galileo_Galilei")
SOURCE_ARTICLES_DIR = Path("/home/chan/code/wiki/gwiki/wiki/A/")
SOURCE_IMAGES_DIR = Path("/home/chan/code/wiki/gwiki/wiki/I/")
TARGET_ARTICLE_DIR = Path("/home/chan/code/git/blog/wiki/A/")
TARGET_IMAGES_DIR = Path("/home/chan/code/git/blog/wiki/I/")

LAYOUT_FILE = Path("home/chan/code/git/blog/wiki/layout.html")

BROKEN_LINK_HREF = "../not_g.html"
BROKEN_LINK_CLASS = "not_g"  # Inline style for broken links color:#BF3C2C

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("wiki_processing.log"),  # Log file
        logging.StreamHandler(sys.stdout),
    ],
)


# Check folder for filenames of articles, select only the the ones that start with G.
# All Articles are in A/ and are in the format of A/Article_Name A/Article_name,Example(parenthesis) A/SubDirectory/Article
def get_g(src_dir: Path) -> list[Path]:
    """Return sorted list of Paths for files whose basename starts with G (case-sensitive)."""
    return {
        p.name: p for p in src_dir.iterdir() if p.is_file() and p.name.startswith("G")
    }


def load_layout() -> str:
    try:
        return LAYOUT_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        logging.error(f"Layout file not found: {LAYOUT_FILE}")
        sys.exit(1)


def slug(text: str) -> str:
    return re.sub(r"\s+", "_", text.strip())


def rewrite_links(soup: BeautifulSoup, g_names: set[str]):
    """Mutate <a> tags: keep G-links, mark others broken."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        target = href.split("#", 1)[0]  # strip fragment
        target = target[:-5] if target.endswith(".html") else target
        if not target or target in g_names:
            a["href"] = f"{target}.html" if not href.endswith(".html") else href
        else:
            a["href"] = BROKEN_LINK_HREF
            a["class"] = a.get("class", []) + [BROKEN_LINK_CLASS]


def first_snippet(soup: BeautifulSoup, max_chars=140) -> str:
    p = soup.find("p")
    return shorten(p.get_text(" ", strip=True), max_chars) if p else ""


def wrap_html(body_html: str, title: str, layout_tpl: str) -> str:
    return layout_tpl.replace("{{TITLE}}", title).replace("{{CONTENT}}", body_html)


def collect_images(soup: BeautifulSoup):
    return sorted(
        {img.get("src", "") for img in soup.find_all("img") if img.get("src")}
    )


def copy_images(img_src_list: set[str]):
    TARGET_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in img_src_list:
        name = Path(src).name
        src_path = SOURCE_IMAGES_DIR / name
        dest_path = TARGET_IMAGES_DIR / name
        if src_path.exists() and not dest_path.exists():
            try:
                shutil.copy2(src_path, dest_path)
                copied += 1
            except Exception as e:
                logging.warning(f"Copy failed for {name}: {e}")
    logging.info(f"Copied {copied} images to {TARGET_IMAGES_DIR}")


def main():
    ap = argparse.ArgumentParser(description="Process G-articles into wrapped wikis")
    ap.add_argument(
        "--json", default="articles.json", help="Path for generated article index JSON"
    )
    ap.add_argument(
        "--list",
        type=Path,
        help="File containing basenames (one per line) to process exactly",
    )
    ap.add_argument(
        "--wrap-only",
        action="store_true",
        help="Re‑wrap existing files in TARGET_ARTICLE_DIR only",
    )
    ap.add_argument(
        "--images",
        action="store_true",
        help="Copy required images from source to target",
    )
    args = ap.parse_args()

    TARGET_ARTICLE_DIR.mkdir(parents=True, exist_ok=True)
    layout = load_layout()

    # ── WRAP‑ONLY MODE ───────────────────────────────────────────────
    if args.wrap_only:
        paths = sorted(TARGET_ARTICLE_DIR.glob("*.html"))
        logging.info(f"Re‑wrapping {len(paths)} existing articles…")
        images_needed = set()

        for path in tqdm(paths, unit="file"):
            soup = BeautifulSoup(
                path.read_text(encoding="utf-8", errors="ignore"), "html.parser"
            )

            # Extract original content inside main#article-wrap if present
            content_tag = soup.find(id="article-wrap") or soup.body or soup
            article_html = "".join(str(c) for c in content_tag.contents)
            title_tag = soup.find("title")
            title = (
                title_tag.string.strip()
                if title_tag and title_tag.string
                else path.stem
            )

            out_html = wrap_html(article_html, title, layout)
            path.write_text(out_html, encoding="utf-8")

            if args.images:
                images_needed.update(collect_images(content_tag))

        if args.images:
            copy_images(images_needed)
        logging.info("✓ Wrap‑only complete")
        return

    all_g = get_g(SOURCE_ARTICLES_DIR)

    if args.list:
        wanted = [
            line.strip() for line in args.list.read_text().splitlines() if line.strip()
        ]
        paths = [all_g[name] for name in wanted if name in all_g]
        missing = [n for n in wanted if n not in all_g]
        if missing:
            logging.warning(
                f"Missing {len(missing)} requested articles: {', '.join(missing)}"
            )
    else:
        paths = sorted(all_g.values())

    valid_names = {p.name for p in paths}
    index = []

    logging.info(f"Processing {len(paths)} articles…")
    for src in tqdm(paths, unit="file"):
        try:
            html = src.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logging.warning(f"Read fail {src.name}: {e}")
            continue

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if not (title_tag and title_tag.string):
            continue
        title = title_tag.string.strip()

        rewrite_links(soup, valid_names)
        snippet = first_snippet(soup)
        images = collect_images(soup)

        out_name = f"{src.name}.html"
        (TARGET_ARTICLE_DIR / out_name).write_text(
            layout.replace("{{TITLE}}", title).replace("{{CONTENT}}", str(soup)),
            encoding="utf-8",
        )

        index.append(
            {
                "title": title,
                "path": f"/wiki/A/{out_name}",
                "snippet": snippet,
                "images": images,
            }
        )

    json_path = TARGET_ARTICLE_DIR.parent / args.json
    json_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logging.info(f"Wrote {len(index)} records → {json_path}\n✓ Done")

    if args.images:
        copy_images(images_needed)
    logging.info("✓ Full processing complete")


if __name__ == "__main__":
    main()
