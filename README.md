# Festival Vendor Directory 🎪✨

Curated directory of independent, handmade festival vendors.

## Quick Start

### Preview Locally
```bash
cd website
python3 -m http.server 8000
```
Open http://localhost:8000

### Deploy to VPS
```bash
# First time setup (installs nginx + SSL)
./scripts/deploy.sh user@host domain.com --setup

# Regular deployments
./scripts/deploy.sh user@host domain.com
```

## Project Status
✅ **COMPLETE** — Ready for deployment

- 526 curated vendors from 1,965 Instagram accounts
- 73.2% rejection rate (highly curated)
- Static website with search/filter
- Deployment scripts ready

## Documentation
- **PROJECT_SUMMARY.md** — Complete project report
- **IMPLEMENTATION_GUIDE.md** — Architecture details
- **PREVIEW.md** — Local testing guide

## Data Pipeline
```bash
# Run curation pipeline
python3 -m curation.run_pipeline --input data.csv --output output/

# Build website data
python3 website/build_site_data.py output/curated_vendors.json website/vendors.json

# Deploy
./scripts/deploy.sh user@host domain.com
```

## Configuration
Edit `curation/config.py` for:
- Keyword lists (YES/NO signals)
- Thresholds (follower counts, scores)
- Categories
- API settings

Environment: `.env` file with `DEEPSEEK_API_KEY`

---

**Built by Bub 🐾 — 2026-02-11**
