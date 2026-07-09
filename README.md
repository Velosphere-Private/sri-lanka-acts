# Sri Lanka Acts (English Only)

This repository publishes an English-only Sri Lanka Acts dataset, maintained independently by scraping the official Sri Lankan government documents website directly.

## What is included

- Acts only (no bills or gazettes)
- English documents only (`lang=en`)
- Folder layout: `{decade}/{year}/{doc_id}/`
- Typical files per act: `doc.json`, `doc.pdf`, `doc.txt`, `blocks.json`, `{description}.html`, optional `tabular_data/*.csv`

## Source

- Primary source website: [documents.gov.lk](https://documents.gov.lk)
- Metadata pages pattern: `https://documents.gov.lk/view/acts/acts_<YEAR>.html`
- PDF links are captured only for English acts (`*_E.pdf`)

## Automatic updates

This repository auto-scrapes and updates using GitHub Actions:

- Workflow: `.github/workflows/update-acts-en.yml` (`Scrape and Update English Sri Lanka Acts`)
- Schedule: daily
- Manual trigger: Actions -> "Update English Sri Lanka Acts" -> Run workflow

## Local update command

```bash
python scripts/sync_english_acts.py
```

The sync script scrapes directly from `documents.gov.lk`, upserts English acts metadata, and removes noisy generated files like `docs_*.tsv`, chart images, and per-document `README.md` files.

## PDF to HTML conversion

Each act PDF is converted to structured HTML using `pdfstruct`. The output filename comes from the `description` field in `doc.json` (for example, `Police Commission.html`).

Local commands:

```bash
# Convert every act PDF in the repo
python scripts/convert_pdfs_to_html.py --all

# Convert only folders whose doc.pdf changed between two git refs
python scripts/convert_pdfs_to_html.py --changed --base-ref HEAD~1 --head-ref HEAD
```

GitHub Actions:

- **Convert All PDFs to HTML** (`.github/workflows/convert-all-pdfs.yml`) — manual full rebuild
- **Convert Changed PDFs to HTML** (`.github/workflows/convert-changed-pdfs.yml`) — runs on push when any `doc.pdf` changes
