#!/usr/bin/env python3
"""
Direct scraper/updater for Sri Lanka Acts (English only).

This script is independent of lk_legal_docs. It scrapes the government acts
listing pages, discovers English PDF links, and upserts `doc.json` metadata.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests

START_YEAR = 1981
DECADE_RE = re.compile(r"^\d{4}s$")
YEAR_RE = re.compile(r"^\d{4}$")
PDF_RE = re.compile(r'href=["\']([^"\']+?_E\.pdf)["\']', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{2}[./-]\d{2}[./-]\d{4})\b"),
]
NUMBER_RE = re.compile(r"(\d+)-(\d{4})_E\.pdf$", re.IGNORECASE)
USER_AGENT = "Mozilla/5.0 (compatible; SriLankaActsBot/1.0)"


@dataclass
class Stats:
    count: int = 0
    min_date: str | None = None
    max_date: str | None = None

    def track_date(self, date_str: str | None) -> None:
        if not date_str:
            return
        if self.min_date is None or date_str < self.min_date:
            self.min_date = date_str
        if self.max_date is None or date_str > self.max_date:
            self.max_date = date_str


def parse_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    parts = re.split(r"[./-]", raw)
    if len(parts) == 3 and len(parts[2]) == 4:
        dd, mm, yyyy = parts
        if dd.isdigit() and mm.isdigit() and yyyy.isdigit():
            return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"
    return None


def clean_text(html_fragment: str) -> str:
    text = TAG_RE.sub(" ", html_fragment)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_year_page(session: requests.Session, year: int) -> tuple[str | None, str | None]:
    candidates = [
        f"https://documents.gov.lk/view/acts/acts_{year}.html",
        f"https://www.documents.gov.lk/view/acts/acts_{year}.html",
    ]
    for url in candidates:
        try:
            response = session.get(url, timeout=40)
            if response.status_code == 200 and "_E.pdf" in response.text:
                return response.text, url
        except requests.RequestException:
            continue
    return None, None


def extract_rows(html: str) -> list[str]:
    rows = re.findall(r"<tr[^>]*>.*?</tr>", html, flags=re.IGNORECASE | re.DOTALL)
    if rows:
        return rows
    return [html]


def extract_year_docs(session: requests.Session, year: int) -> list[dict]:
    html, page_url = get_year_page(session, year)
    if not html or not page_url:
        return []

    docs: list[dict] = []
    seen_urls: set[str] = set()
    for row in extract_rows(html):
        links = PDF_RE.findall(row)
        if not links:
            continue
        text = clean_text(row)

        parsed_date = None
        for pattern in DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                parsed_date = parse_date(match.group(1))
                if parsed_date:
                    break

        for href in links:
            pdf_url = urljoin(page_url, href)
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            file_name = pdf_url.rstrip("/").split("/")[-1]

            number_match = NUMBER_RE.search(file_name)
            act_number = None
            doc_number = None
            if number_match:
                act_number = int(number_match.group(1))
                doc_number = f"{number_match.group(1)}/{number_match.group(2)}"

            description = text
            if description:
                description = re.sub(r"\s*English\s*", " ", description, flags=re.IGNORECASE)
                description = re.sub(r"\s+", " ", description).strip(" -:")

            if not parsed_date:
                parsed_date = f"{year}-01-01"

            doc_id = f"{parsed_date}-{parsed_date}-{act_number or file_name}-{year}-en"
            doc_id = re.sub(r"[^a-zA-Z0-9._/-]", "-", doc_id)

            docs.append(
                {
                    "doc_type": "lk_acts",
                    "doc_id": doc_id,
                    "num": f"{act_number or file_name}-{year}-en",
                    "date_str": parsed_date,
                    "description": description,
                    "url_metadata": page_url,
                    "lang": "en",
                    "url_pdf": pdf_url,
                    "doc_number": doc_number,
                }
            )
    return docs


def remove_noisy_files(repo_root: Path) -> None:
    for file_name in [
        "docs_all.tsv",
        "docs_last100.tsv",
        "docs_last1000.tsv",
        "docs_last10000.tsv",
        "docs_by_decade_and_lang.png",
    ]:
        target = repo_root / file_name
        if target.exists():
            target.unlink()

    for readme in repo_root.glob("**/README.md"):
        if readme.parent == repo_root:
            continue
        readme.unlink(missing_ok=True)


def ensure_doc(repo_root: Path, doc: dict) -> None:
    year = int(doc["date_str"][:4])
    decade = f"{year // 10 * 10}s"
    doc_dir = repo_root / decade / str(year) / doc["doc_id"]
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "doc.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def scan_existing(repo_root: Path) -> Stats:
    stats = Stats()
    for decade in repo_root.iterdir():
        if not decade.is_dir() or not DECADE_RE.match(decade.name):
            continue
        for year_dir in decade.iterdir():
            if not year_dir.is_dir() or not YEAR_RE.match(year_dir.name):
                continue
            for doc_dir in year_dir.iterdir():
                doc_json = doc_dir / "doc.json"
                if not doc_json.exists():
                    continue
                stats.count += 1
                try:
                    data = json.loads(doc_json.read_text(encoding="utf-8"))
                    stats.track_date(data.get("date_str"))
                except json.JSONDecodeError:
                    continue
    return stats


def write_summary(repo_root: Path, stats: Stats) -> None:
    summary = {
        "dataset": "Sri Lanka Acts (English only)",
        "source": "https://documents.gov.lk",
        "source_note": "Scraped directly from official acts listing pages",
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "n_docs": stats.count,
        "date_str_min": stats.min_date,
        "date_str_max": stats.max_date,
        "langs": ["en"],
    }
    (repo_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    repo_root = Path.cwd()
    remove_noisy_files(repo_root)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    current_year = datetime.now(timezone.utc).year
    for year in range(START_YEAR, current_year + 1):
        for doc in extract_year_docs(session, year):
            ensure_doc(repo_root, doc)

    stats = scan_existing(repo_root)
    write_summary(repo_root, stats)
    print(f"Dataset ready: {stats.count} docs ({stats.min_date}..{stats.max_date})")


if __name__ == "__main__":
    main()
