#!/usr/bin/env python3
"""
Convert act PDFs to HTML using pdfstruct.

Reads the act title from doc.json `description` and writes
`{sanitized-description}.html` next to doc.pdf in each act folder.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DECADE_RE = re.compile(r"^\d{4}s$")
YEAR_RE = re.compile(r"^\d{4}$")
UNSAFE_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def default_pdfstruct_path(repo_root: Path) -> Path:
    return repo_root / "tools" / "pdfstruct-linux-x86_64" / "pdfstruct"


def sanitize_description(description: str) -> str:
    name = UNSAFE_CHARS_RE.sub(" ", description or "untitled")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "untitled"


def html_filename(description: str) -> str:
    return f"{sanitize_description(description)}.html"


def iter_act_dirs(repo_root: Path) -> list[Path]:
    act_dirs: list[Path] = []
    for decade in sorted(repo_root.iterdir()):
        if not decade.is_dir() or not DECADE_RE.match(decade.name):
            continue
        for year_dir in sorted(decade.iterdir()):
            if not year_dir.is_dir() or not YEAR_RE.match(year_dir.name):
                continue
            for doc_dir in sorted(year_dir.iterdir()):
                if (doc_dir / "doc.pdf").is_file():
                    act_dirs.append(doc_dir)
    return act_dirs


def changed_pdf_dirs(repo_root: Path, base_ref: str, head_ref: str) -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base_ref, head_ref, "--", "**/doc.pdf"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")

    act_dirs: list[Path] = []
    seen: set[Path] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.endswith("/doc.pdf") and not line.endswith("\\doc.pdf"):
            continue
        doc_dir = (repo_root / line).parent.resolve()
        if doc_dir in seen:
            continue
        seen.add(doc_dir)
        if (doc_dir / "doc.pdf").is_file():
            act_dirs.append(doc_dir)
    return sorted(act_dirs)


def load_description(doc_dir: Path) -> str:
    doc_json_path = doc_dir / "doc.json"
    if not doc_json_path.is_file():
        raise FileNotFoundError(f"missing doc.json in {doc_dir}")
    data = json.loads(doc_json_path.read_text(encoding="utf-8"))
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"missing description in {doc_json_path}")
    return description.strip()


def remove_stale_html(doc_dir: Path, keep_name: str) -> None:
    for html_file in doc_dir.glob("*.html"):
        if html_file.name != keep_name:
            html_file.unlink()


def convert_act_dir(doc_dir: Path, pdfstruct: Path) -> Path:
    doc_pdf = doc_dir / "doc.pdf"
    if not doc_pdf.is_file():
        raise FileNotFoundError(f"missing doc.pdf in {doc_dir}")

    description = load_description(doc_dir)
    output_name = html_filename(description)
    output_path = doc_dir / output_name

    subprocess.run(
        [str(pdfstruct), str(doc_pdf), "-o", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    remove_stale_html(doc_dir, output_name)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert act PDFs to HTML with pdfstruct.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="Convert every act PDF in the repo.")
    scope.add_argument(
        "--changed",
        action="store_true",
        help="Convert only act folders whose doc.pdf changed between two git refs.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Base git ref for --changed (default: HEAD~1).",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Head git ref for --changed (default: HEAD).",
    )
    parser.add_argument(
        "--pdfstruct",
        type=Path,
        default=None,
        help="Path to pdfstruct binary (default: tools/pdfstruct-linux-x86_64/pdfstruct).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = repo_root_from_script()
    pdfstruct = args.pdfstruct or default_pdfstruct_path(repo_root)

    if not pdfstruct.is_file():
        print(f"pdfstruct not found: {pdfstruct}", file=sys.stderr)
        return 1

    if args.all:
        act_dirs = iter_act_dirs(repo_root)
    else:
        act_dirs = changed_pdf_dirs(repo_root, args.base_ref, args.head_ref)

    if not act_dirs:
        print("No act PDFs to convert.")
        return 0

    converted = 0
    failed = 0
    for doc_dir in act_dirs:
        try:
            output_path = convert_act_dir(doc_dir, pdfstruct)
            converted += 1
            print(f"converted: {output_path.relative_to(repo_root)}")
        except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
            failed += 1
            print(f"failed: {doc_dir.relative_to(repo_root)} ({exc})", file=sys.stderr)

    print(f"Done: {converted} converted, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
