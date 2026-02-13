# Festival Vendor Directory — Full Implementation Guide

## Architecture Overview

```
SCRAPED CSV (2K–20K records)
    │
    ▼
┌─────────────────────────────────┐
│  PHASE 1: CURATION PIPELINE     │
│                                 │
│  Step 1: data_loader.py         │  ← Load + normalize CSV
│      │                          │
│  Step 2: rules_engine.py        │  ← Fast pass: YES/NO/MAYBE
│      │                          │     (~70% classified here)
│  Step 3: llm_curator.py         │  ← DeepSeek classifies MAYBEs
│      │                          │     (batched, resumable)
│  Step 4: category_tagger.py     │  ← Assign vendor categories
│      │                          │
│  Output: curated_vendors.json   │
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  PHASE 2: WEBSITE               │
│                                 │
│  Static site (no backend)       │
│  - index.html (single page)     │
│  - vendors.json (data file)     │
│  - Client-side search/filter    │
│                                 │
│  Deploy: nginx static files     │
└─────────────────────────────────┘
```

## File Structure

```
festival-vendor-directory/
├── IMPLEMENTATION_GUIDE.md        # This file
├── curation/
│   ├── config.py                  # All tunables: thresholds, keywords, API keys
│   ├── data_loader.py             # CSV ingestion + normalization
│   ├── rules_engine.py            # Deterministic YES/NO/MAYBE classification
│   ├── llm_curator.py             # DeepSeek API calls for MAYBE records
│   ├── category_tagger.py         # Assign browseable categories via LLM
│   ├── run_pipeline.py            # Orchestrator: runs all steps in sequence
│   └── test_curation.py           # Sanity checks against known YES/NO examples
├── website/
│   ├── index.html                 # Single-page directory (mobile-first)
│   ├── vendors.json               # Generated data file website reads
│   └── build_site_data.py         # Transforms curated_vendors.json → vendors.json
├── scripts/
│   ├── setup.sh                   # Install dependencies
│   └── deploy.sh                  # Deployment to VPS
└── output/
    ├── rules_output.csv           # After rules pass (intermediate)
    ├── curated_vendors.json       # After LLM pass (final curation)
    └── curated_vendors.csv        # CSV export for human review
```

## Answers to Open Questions

### 1. Category Taxonomy
Auto-generated via LLM in `category_tagger.py`. The LLM assigns 1-2 categories from a fixed list based on bio + website description. Fixed list (tunable in config):
- Festival Clothing
- Jewelry & Accessories
- Art & Prints
- Home Decor
- Toys & Sculptures
- Bags & Packs
- Body Art & Cosmetics
- Stickers & Patches
- Music & Instruments
- Other Handmade

### 2. Data Enrichment
Post-curation only. Scraping 20K vendor websites pre-curation wastes resources on accounts that won't make the cut. The scraped bio + website meta descriptions are sufficient for curation.

### 3. Image Sourcing
MVP: Instagram profile pic URL (already in data via profileURL construction). Phase 2 polish: scrape hero images from vendor sites for the ~200-400 that made the cut.

### 4. Update Strategy
`run_pipeline.py` has `--incremental` flag. It checks for existing output, skips already-processed usernames, and only scores new records. Re-scoring requires `--full` flag.

## Hosting Decisions

### Recommendation: Static Site
A filterable directory of 200-400 vendors is a perfect static site use case. No backend needed — all filtering happens client-side with JavaScript.

**Why not Node.js?** Zero benefit for this. The data changes weekly at most (re-run pipeline, regenerate vendors.json, rsync). A static site is faster, cheaper, and Bub can deploy it with zero process management.

### VPS Recommendation
**Hetzner Cloud CX22** — €4.51/mo (~$5 USD)
- 2 vCPU, 4GB RAM, 40GB disk
- More than enough for static hosting + occasional pipeline runs
- Great EU/US peering

Alternative: **Oracle Cloud Free Tier** — literally $0, 1 OCPU + 1GB RAM, enough for static hosting (pipeline runs locally on WSL2).

### Domain Strategy
Register a new domain. Something like `trippyvendors.com`, `festfind.co`, `psymarket.directory`. ~$10/yr on Namecheap or Cloudflare Registrar.

### Deployment Flow
1. Dan provisions VPS + domain (one-time, ~15 min)
2. Bub handles: nginx config, SSL (certbot), git deploy, cron for auto-updates

## Cost Estimate (20K Records)

### DeepSeek API Costs
- Rules engine classifies ~70% deterministically → ~6,000 records need LLM
- Category tagging on ~300 curated vendors → ~300 calls
- DeepSeek Chat pricing: ~$0.14/M input tokens, ~$0.28/M output tokens
- Average prompt: ~200 tokens input, ~50 tokens output per record
- **Curation: 6,000 × 200 = 1.2M input tokens = $0.17**
- **Curation: 6,000 × 50 = 300K output tokens = $0.08**
- **Category tagging: 300 × 250 = 75K input tokens = ~$0.01**
- **Total estimated cost: ~$0.30 per full pipeline run**

Batching 10 records per API call reduces this further to ~$0.10-0.15.

---

## EXECUTION TASKS

Tasks are designed to be run sequentially. Each produces a verifiable output.

---

### TASK 1: Setup & Dependencies

**Purpose:** Install Python packages needed for the pipeline.

**Commands:**
```bash
pip install pandas requests python-dotenv --break-system-packages
```

**Also create `.env` file:**
```bash
echo "DEEPSEEK_API_KEY=your_key_here" > .env
```

**Verify:** `python -c "import pandas, requests, dotenv; print('OK')"`

---

### TASK 2: Configuration Module

**Purpose:** Single source of truth for all tunables.

**File:** `curation/config.py`

**Verify:** `python -c "from curation.config import *; print(CATEGORIES)"`

---

### TASK 3: Data Loader

**Purpose:** Load and normalize the scraped CSV into a clean DataFrame.

**File:** `curation/data_loader.py`

**Verify:** `python -c "from curation.data_loader import load_data; df = load_data('path/to/scraped.csv'); print(f'{len(df)} records loaded'); print(df.columns.tolist())"`

---

### TASK 4: Rules Engine

**Purpose:** Fast deterministic classification. This is the workhorse that keeps LLM costs down.

**File:** `curation/rules_engine.py`

**Verify:** Run against sample data, confirm known YES examples score > 0.6, known NO examples score < 0.3, and ~60-70% of records get a definitive YES or NO.

---

### TASK 5: LLM Curator

**Purpose:** Send MAYBE records to DeepSeek for nuanced classification.

**File:** `curation/llm_curator.py`

**Verify:** Test with 5 MAYBE records, confirm responses parse correctly and scores are 0-1.

---

### TASK 6: Category Tagger

**Purpose:** Assign browseable categories to curated vendors.

**File:** `curation/category_tagger.py`

**Verify:** Run on 5 known vendors, confirm categories make sense.

---

### TASK 7: Pipeline Orchestrator

**Purpose:** Single entry point that chains all steps.

**File:** `curation/run_pipeline.py`

**Verify:** `python -m curation.run_pipeline --input scraped.csv --output output/` should produce `curated_vendors.json` and `curated_vendors.csv`.

---

### TASK 8: Test Suite

**Purpose:** Validate curation accuracy against known examples.

**File:** `curation/test_curation.py`

**Verify:** `python -m curation.test_curation` — all known YES/NO examples classified correctly.

---

### TASK 9: Website Build Script

**Purpose:** Transform curated data into the JSON format the website expects.

**File:** `website/build_site_data.py`

**Verify:** Produces `website/vendors.json` with expected schema.

---

### TASK 10: Directory Website

**Purpose:** Single-page, mobile-first, filterable vendor directory.

**File:** `website/index.html`

**Verify:** Open in browser, search works, category filters work, mobile responsive.

---

### TASK 11: Deployment Scripts

**Purpose:** Automated setup and deploy for VPS.

**Files:** `scripts/setup.sh`, `scripts/deploy.sh`

**Verify:** After Dan provisions VPS, Bub runs setup.sh once, then deploy.sh pushes site live.
