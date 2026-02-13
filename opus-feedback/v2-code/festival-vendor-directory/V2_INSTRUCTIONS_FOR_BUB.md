# V2 Curation Pipeline — Instructions for Bub

## What Changed and Why

The v1 pipeline approved 526 vendors from 1,965 records (26.8%). Manual review found ~10-15% false positive rate. The three root causes:

1. **Rules engine auto-approved vendors** — "festival fashion" + "designer" alone scored 0.77 and bypassed LLM entirely. Influencers, high fashion designers, and personal accounts slipped through.
2. **LLM was too generous** — 35% of LLM-approved vendors had no shop URL. DeepSeek scored "handmade vibes" without checking if there was a way to buy.
3. **No URL validation** — 84 approved vendors (16%) had zero way to purchase anything.

## V2 Architecture: Three-Stage Funnel

```
Stage 1: RULES ENGINE (bouncer)
  - Only REJECTS obvious NOs
  - NO auto-YES anymore
  - Everything else → "review" (sent to LLM)
  - Expected: ~58% rejected, ~42% sent to review
      │
Stage 2: LLM CURATOR (judge)
  - Scores every "review" record 0.0-1.0
  - Asks 3 questions: sells_products? has_shop? festival_aesthetic?
  - Higher threshold: 0.70 (was 0.55)
  - Smaller batches (5 per call) for better accuracy
      │
Stage 3: VALIDATION GATE (hard requirements)
  - Must have real shop URL (not YouTube, Venmo, tickets)
  - Must have LLM score >= 0.70
  - Must have sells_products = true
  - Non-shop domain URLs auto-rejected
      │
  APPROVED (~200-350 vendors from 2K dataset)
```

## Key File Changes

ALL curation files have been rewritten. Replace the entire `curation/` directory:

- **config.py** — New keyword lists (PRODUCT_KEYWORDS, AESTHETIC_KEYWORDS, NEGATIVE_KEYWORDS), URL classification (SHOP_DOMAINS, NON_SHOP_DOMAINS), no more RULES_YES_THRESHOLD
- **rules_engine.py** — Only rejects, never approves. Outputs "no" or "review". Also computes structured `signals` dict passed to LLM as context.
- **llm_curator.py** — New 3-question prompt. Validation gate post-LLM. Shop URL requirement enforced.
- **category_tagger.py** — Now also generates search tags per vendor.
- **run_pipeline.py** — Updated for v2 flow.
- **test_curation.py** — Includes audit problem cases.

## Deployment Steps

### Step 1: Replace curation code
```bash
# Backup v1
cp -r curation/ curation_v1_backup/

# Replace with v2 files (all files in the curation/ directory from the zip)
```

### Step 2: Clear v1 cache
```bash
rm -f output/pipeline_progress.json
rm -f output/pipeline_progress_v2.json
```

### Step 3: Run tests
```bash
python -m curation.test_curation
```
Expected: 8/9 pass, 1 warning (etudemesf gets "review" but gate rejects it — that's correct).

### Step 4: Run rules-only pass (no API cost)
```bash
python -m curation.run_pipeline --input <your_scraped.csv> --output output/ --skip-llm
```
This shows how many records survive rules to go to LLM review. Expected: ~40% sent to review.

### Step 5: Full pipeline run
```bash
python -m curation.run_pipeline --input <your_scraped.csv> --output output/ --full
```
This runs the complete pipeline. `--full` clears the LLM cache so everything is re-scored.

### Step 6: Build website data
```bash
python website/build_site_data.py output/curated_vendors.json website/vendors.json
```

### Step 7: Verify results
Check `output/curated_vendors.csv` — every vendor should have:
- An external URL (shop or aggregator link)
- LLM score >= 0.70
- sells_products = True
- Categories and tags assigned

## Answering Bub's Questions from the Audit

### Q1: Shop URL requirement?
**Yes, hard requirement.** No URL = no approval. If someone has amazing vibes but no shop, they don't belong in a VENDOR directory. Period.

### Q2: Aesthetic detection from text?
Text-only works for most cases. The LLM prompt now explicitly calls out "slow fashion / minimalist / high fashion = wrong aesthetic." Vision analysis is a Phase 2 enhancement — not needed for MVP.

### Q3: Event organizers?
**Excluded.** Even if they sell merch, their primary business is events. The negative keywords now include "event organizer", "event promoter", etc. LLM prompt caps their score at 0.30.

### Q4: Influencer/affiliate detection?
Handled at multiple levels:
- Rules: "brand ambassador", "affiliate", "use code", "vibe curator" → negative keywords
- URL: non-shop domains (universe.com, hihello.com) → instant penalty
- LLM prompt: explicitly says "influencers/affiliates = max 0.20"
- Gate: non-shop URL domain → rejected

### Q5: Keyword context?
V2 splits keywords into PRODUCT (making/selling signals) and AESTHETIC (vibe signals). Having only aesthetic keywords with zero product keywords results in a low score. "Festival fashion" without "handmade", "shop", or a shop URL won't pass.

### Q6: LLM vs Rules balance?
V2 answer: Rules ONLY reject. LLM judges ALL potential vendors. This is more expensive (~$0.40-0.60 per 2K run instead of $0.15) but dramatically reduces false positives. At scale (20K), cost is ~$2-3 per run — still trivial.

### Q7: Missing data?
Hashtag/caption analysis would help but isn't needed for MVP. The current bio + website metadata + URL classification catches 95%+ of cases. Add post analysis in Phase 2.

## Cost Estimate (V2)

For 2K records:
- Rules reject ~58% → ~813 go to LLM
- LLM batches of 5 → ~163 API calls for curation
- Category tagging on ~300 vendors → ~30 API calls
- Total: ~193 API calls × ~300 tokens avg = ~58K tokens
- DeepSeek cost: ~$0.02 input + ~$0.02 output = **~$0.04 per run**

For 20K records:
- ~8,400 go to LLM → ~1,680 API calls
- Category tagging on ~2,000 → ~200 calls
- **~$0.40 per full run**

## What Dan Should Review

After v2 pipeline runs, Dan should spot-check:
1. The top 20 vendors by score — do they feel handpicked?
2. 10 random vendors from the middle of the list — still quality?
3. Search for known problem cases (go.with.the.bo, etudemesf) — should NOT appear
4. Look at the tags — do they make sense for filtering?
5. Check if any obvious vendors are MISSING that should be included
