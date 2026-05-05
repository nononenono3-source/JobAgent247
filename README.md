# JobAgent247 (Zero-cost Job Posting Ecosystem)

This repo is designed to run **100% autonomously on GitHub Actions**:
- Fetch global job listings from **Adzuna (free tier)**
- Categorize for **Freshers (0–1 yrs)** and **Pros (3+ yrs)**
- Generate Instagram carousels, YouTube shorts, and PDFs (next steps)

## Setup (later steps will expand this)

### GitHub Secrets you will add
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scraper.py --country in --pages 2
```

## Phase 2 (Visuals + PDF)

### Generate Instagram carousel slides
Requires you have `data/jobs.json` from `scraper.py`.

```bash
python designer.py --in data/jobs.json
```

Outputs PNG slides under `assets/carousels/<timestamp>/slide_XX.png`.

### Generate PDF into `/docs` (GitHub Pages)

```bash
python pdf_generator.py --in data/jobs.json --docs-dir docs
```

This writes:
- A timestamped PDF: `docs/jobs-<timestamp>.pdf`
- An index page: `docs/index.html` (links to all PDFs)
- A stable alias: `docs/latest-jobs.pdf` (for social links)

## Phase 3 (Video + Automation)

### Generate a YouTube Shorts video (60s) + thumbnail
This uses the **latest** carousel batch under `assets/carousels/`.

```bash
python video_maker.py --jobs data/jobs.json --pages-url "https://<you>.github.io/<repo>/docs/latest-jobs.pdf"
```

### Run the full orchestrator

```bash
python main.py --mode youtube
python main.py --mode instagram --no-upload
```



