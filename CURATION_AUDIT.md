# Curation Pipeline Audit — For Opus Review

**Purpose:** Audit and refine the vendor classification logic  
**Current State:** 526 vendors approved from 1,965 Instagram accounts (26.8% approval rate)  
**Goal:** Improve accuracy, reduce false positives, clarify scoring logic

---

## Executive Summary

The curation pipeline uses a two-stage approach:
1. **Rules Engine** (deterministic keyword/follower scoring) → classifies 64.8% of records
2. **LLM Curator** (DeepSeek) → reviews ambiguous "maybe" cases (35.2%)

**Problem:** Several false positives found during manual review, revealing gaps in both rules and LLM logic.

---

## How Classification Works

### Stage 1: Rules Engine (rules_score → rules_classification)

**Input:** Instagram profile data (bio, followers, external URL, business flag)  
**Output:** Score 0.0-1.0 + classification (YES/NO/MAYBE)

**Scoring logic:**
```
Starting score: 0.5 (neutral)

POSITIVE SIGNALS:
+0.08 per strong keyword (handmade, artisan, etc.) — max +0.35
+0.03 per weak keyword (art, creative, festival) — max +0.15
+0.15 if shop URL pattern detected (etsy.com/shop, bigcartel, etc.)
+0.15 if marketplace URL (etsy, bigcartel, storenvy)
+0.08 if business account flag
+0.05 if has any external URL
+0.05 if follower count 1K-50K (small business sweet spot)
+0.02 if link aggregator (linktree, bio.fm)

NEGATIVE SIGNALS:
-0.12 per negative keyword (DJ, producer, speaker, yoga, etc.) — max -0.40
-0.15 if followers > 500K (too big = likely brand)
-0.20 if "shipping worldwide" + high followers (big brand pattern)

INSTANT DISQUALIFIERS (score → 0.0):
- Known big brand domain (iheartraves.com, dollskill.com, etc.)
- Followers > 500K (big brand threshold)
- Followers < 200 (too small = not established)
- No bio, no URL, no data to evaluate
- Personal account pattern (no URL, not business, high follow ratio, no vendor keywords)
```

**Thresholds:**
- `rules_score >= 0.70` → **YES** (skip LLM)
- `rules_score <= 0.25` → **NO** (skip LLM)
- `0.25 < rules_score < 0.70` → **MAYBE** (send to LLM)

**Result:** 64.8% classified (390 YES, 883 NO), 35.2% MAYBE (692 records)

---

### Stage 2: LLM Curator (llm_score → final_classification)

**Input:** Only MAYBE records from rules engine (0.25 < score < 0.70)  
**Model:** DeepSeek Chat  
**Batch size:** 10 records per API call

**Prompt:** (summarized)
```
Review these Instagram accounts. Score 0.0-1.0 for festival vendor fit.

CRITERIA:
- Small/independent (not big brands)
- Handmade, unique, creative products
- Festival-appropriate (trippy, psychedelic, bohemian, rave wear)
- Actual product vendors (not DJs, photographers, influencers)

Score 0.0 = definitely not a vendor
Score 1.0 = perfect fit
```

**Final classification logic:**
```python
if rules_classification == "yes":
    final_score = rules_score
    final_classification = "yes"
elif rules_classification == "no":
    final_score = rules_score
    final_classification = "no"
elif rules_classification == "maybe":
    final_score = llm_score
    final_classification = "yes" if llm_score >= 0.55 else "no"
```

**Key insight:** Rules YES/NO decisions bypass LLM entirely. Only MAYBE cases get LLM review.

---

## Problems Found During Manual Review

### 1. Influencer/Affiliate Accounts Approved as Vendors

**Case:** `@go.with.the.bo`
```
Bio: "Part-time Raver 🪩 Full-time Vibe Curator
      Festival Fashion 📍CLT, NC
      👇@breakawaycarolina tix 🎫"
External URL: https://www.universe.com/events/breakaway-carolina-2026-tickets...
Followers: 566

Rules score: 0.75 → YES
Final classification: YES
Categories: ["Festival Clothing"]
```

**Issue:**
- Not a vendor — this is an influencer with an affiliate/ticket link
- "Festival Fashion" triggered +0.08 strong keyword
- "Raver" triggered +0.03 weak keyword
- External URL gave +0.05 (but it's not a shop!)
- Never reached LLM (rules said YES)

**Root cause:** Rules engine doesn't distinguish between shop URLs and affiliate/ticket/profile links.

**Proposed fix:**
- Require shop URL pattern for YES classification
- Add "vibe curator", "full-time raver" to personal account signals
- Penalize .universe.com, eventbrite links (event tickets, not shops)

---

### 2. High Fashion Misclassified as Festival Fashion

**Case:** `@etudemesf`
```
Bio: "ETUDE ME . San Francisco . 🌷♥️
      Independent Fashion Designer
      Sustainably Made in San Francisco
      Dreaming in Slow Fashion🪄✨🪡🧵"
External URL: (none)
Followers: 6,345

Rules score: 0.77 → YES
Final classification: YES
Categories: ["Festival Clothing"]
```

**Issue:**
- This is high fashion / slow fashion, not trippy/festival fashion
- "Independent Fashion Designer" triggered +0.08 (contains "designer")
- Business account flag gave +0.08
- Follower count in sweet spot gave +0.05
- Never reached LLM (rules said YES)

**Root cause:** "Designer" keyword is too broad. Need to distinguish aesthetic styles.

**Proposed fix:**
- Require trippy/festival/psychedelic/bohemian context for fashion
- Add "slow fashion", "minimalist", "elegant" as negative or neutral signals
- Consider LLM review for all fashion accounts (visual aesthetic matters)

---

### 3. Vendors Without Shop Links Approved

**Case:** `@_sewciopath__`
```
Bio: "Sewciopath is a person with an antisocial sewing disorder.
      Thinking only of their next project & about buying fabric ~
      they can never get enough!"
External URL: (none)
Followers: 551

Rules score: 0.58 → MAYBE (correct!)
LLM score: 0.8 → "Sewing projects, handmade, small independent creator"
Final classification: YES
Categories: ["Other Handmade"]
```

**Issue:**
- Clear creator, but NO WAY TO BUY (no external URL, no shop link)
- Rules correctly flagged as MAYBE (0.58)
- LLM approved based on "handmade" signals, ignoring lack of shop

**Root cause:** LLM prompt doesn't emphasize "must have a way to purchase"

**Proposed fix:**
- Add to LLM criteria: "Must have shop link or clear purchase path"
- Penalize absence of external URL more heavily in rules
- Consider requiring external URL for final YES classification

---

### 4. Event Promotion Groups Approved

**Finding:** (Dan mentioned this but didn't provide username)
```
Rules score: 0.63 → MAYBE
Final classification: YES (0.9)
Categories: ["Other Handmade"]
```

**Issue:**
- Event promotion groups sell merch but are primarily event organizers
- Trippy art/aesthetic matches festival vibe
- LLM approved based on "sells merch"

**Root cause:** Unclear boundary — when is merch sales a "vendor" vs "event with merch"?

**Proposed fix:**
- Add "event promoter", "festival organizer" to negative keywords
- LLM should distinguish primary business (events) vs secondary (merch)
- Consider separate category or exclusion for event organizers

---

### 5. Personal Raver Accounts Approved

**Finding:** Personal account with "raver" in bio got MAYBE classification

**Issue:**
- "Raver" is a weak positive keyword (+0.03)
- But most ravers are not vendors
- Should be filtered earlier

**Root cause:** "Raver" keyword is too weak as vendor signal

**Proposed fix:**
- Remove "raver" from weak positive keywords
- Add "personal raver", "rave fam" to personal account signals
- Require additional vendor signals (shop URL, product keywords)

---

## Data Being Filtered

**Current sources:**
- **Bio** (biography field)
- **Website metadata** (title, description, OG tags)
- **all_text** (concatenation of bio + website fields, lowercased)

**Follower metrics:**
- follower count
- following count
- following-to-follower ratio

**Flags:**
- is_business (Instagram business account)
- External URL presence
- Domain extraction from URL

**What's NOT being filtered:**
- Post content (captions, hashtags)
- Visual aesthetic (images, color palette)
- Engagement rate (likes, comments)
- Product prices or inventory
- Shipping information

---

## Proposed Improvements

### 1. Shop URL Requirement

**Problem:** Accounts approved without purchase paths

**Solution:**
```python
# In rules_engine.py, for YES classification:
if score >= RULES_YES_THRESHOLD:
    # Additional check: must have shop URL for auto-YES
    if not _has_shop_url(external_url) and not any(m in domain for m in MARKETPLACE_DOMAINS):
        # Downgrade to MAYBE if no shop URL
        classification = "maybe"
        reasons.append("(downgraded to MAYBE: no shop URL detected)")
    else:
        classification = "yes"
```

**Impact:** Prevents influencers/personal accounts from auto-approval

---

### 2. Aesthetic Classification (LLM)

**Problem:** Can't distinguish high fashion from festival fashion with keywords alone

**Solution:** Add aesthetic tagging to LLM prompt
```
For fashion/clothing vendors, assess aesthetic fit:
- Festival/trippy: psychedelic, colorful, bohemian, rave wear, flow props
- High fashion: elegant, minimalist, sustainable, slow fashion → EXCLUDE
- Streetwear: urban, hype brands → EXCLUDE unless handmade/unique
```

**Alternative:** Use vision model to analyze Instagram grid aesthetic (future enhancement)

---

### 3. Refined Keyword Lists

**Add to STRONG_NO_KEYWORDS:**
```python
"vibe curator", "full-time raver", "part-time raver",
"event promoter", "festival organizer",
"slow fashion", "minimalist fashion",
"brand ambassador", "affiliate",
```

**Remove from WEAK_YES_KEYWORDS:**
```python
"rave", "raver", "festival" (too broad, many personal accounts)
```

**Add context requirements:**
```python
# Only positive if paired with product/vendor signals
CONTEXT_YES_KEYWORDS = ["festival", "rave"]  # require + "shop", "handmade", etc.
```

---

### 4. LLM Prompt Enhancement

**Current prompt weakness:** Doesn't emphasize shop URL requirement

**Improved prompt:**
```
Score each account 0.0-1.0 for vendor directory inclusion:

REQUIRED:
✓ Must sell tangible products (not services, DJ sets, photography)
✓ Must have shop link or clear purchase path (Etsy, BigCartel, website, etc.)
✓ Small/independent (not big brands or mass production)

IDEAL:
✓ Handmade, unique, one-of-a-kind items
✓ Festival aesthetic: psychedelic, trippy, bohemian, colorful, flow toys
✓ Rave/festival wear, art, jewelry, accessories

EXCLUDE:
✗ Personal accounts (no shop link)
✗ Influencers/affiliates (promote but don't create)
✗ DJs, photographers, service providers
✗ Event organizers (even if they sell merch)
✗ High fashion / slow fashion (wrong aesthetic)

Give lower scores (0.3-0.5) if shop link is missing but everything else fits.
```

---

### 5. Post-LLM Validation

**Add final validation step:**
```python
def final_validation(row):
    """Post-LLM check to catch edge cases"""
    
    # If final_classification = YES but no external URL → downgrade to NO
    if row['final_classification'] == 'yes' and not row['external_url']:
        return 'no', 'rejected: no shop link'
    
    # If affiliate/ticket link → downgrade to NO
    affiliate_domains = ['universe.com', 'eventbrite.com', 'dice.fm', 'ticketmaster.com']
    if any(d in str(row['domain']).lower() for d in affiliate_domains):
        return 'no', 'rejected: affiliate/ticket link, not shop'
    
    return row['final_classification'], ''
```

---

## Questions for Opus

1. **Shop URL requirement:**
   - Should we require shop URL for YES classification?
   - Or allow accounts with strong vendor signals but no link (for future follow-up)?

2. **Aesthetic detection:**
   - Can we reliably distinguish festival fashion from high fashion with text alone?
   - Should we add vision model analysis of Instagram grids?

3. **Event organizers:**
   - Where's the line between "vendor" and "event organizer that sells merch"?
   - Should event organizers be a separate category or excluded?

4. **Influencer/affiliate detection:**
   - How to reliably detect affiliate links vs shop links?
   - Should "vibe curator" type bios be auto-rejected?

5. **Keyword context:**
   - Should "festival" + "fashion" require "handmade" or "shop" to be positive?
   - How to handle broad keywords that appear in both vendor and personal accounts?

6. **LLM vs Rules balance:**
   - Current: 64.8% rules, 35.2% LLM
   - Should we move more edge cases to LLM (lower YES_THRESHOLD)?
   - Or tighten rules to reduce false positives?

7. **Missing data:**
   - We don't analyze post content, images, engagement
   - Would hashtag analysis help (e.g., #handmade, #shopsmall)?
   - Would post caption analysis catch missed vendors?

---

## Code Reference

### Rules Engine (rules_engine.py)

```python
def score_record(row: pd.Series) -> dict:
    """
    Score a single record. Returns dict with:
      - score (float 0-1)
      - classification ("yes" | "no" | "maybe")
      - reasons (list of strings explaining the score)
    """
    score = 0.5  # Start neutral
    reasons = []
    all_text = row.get('all_text', '')
    followers = row.get('followers', 0)
    domain = row.get('domain', '')
    external_url = row.get('external_url', '')

    # INSTANT DISQUALIFIERS
    if _is_known_big_brand(domain):
        return {'score': 0.0, 'classification': 'no', 
                'reasons': [f'known big brand domain: {domain}']}
    
    if followers > BIG_BRAND_FOLLOWER_THRESHOLD:
        return {'score': 0.05, 'classification': 'no',
                'reasons': [f'followers ({followers:,}) exceed big brand threshold']}
    
    if followers < MIN_FOLLOWERS:
        return {'score': 0.1, 'classification': 'no',
                'reasons': [f'followers ({followers:,}) below minimum ({MIN_FOLLOWERS})']}
    
    # SCORING SIGNALS
    strong_yes_count = _count_keyword_matches(all_text, STRONG_YES_KEYWORDS)
    if strong_yes_count > 0:
        boost = min(strong_yes_count * 0.08, 0.35)
        score += boost
        reasons.append(f'+{boost:.2f} strong positive keywords ({strong_yes_count} matches)')
    
    # [... more scoring logic ...]
    
    # CLASSIFY
    if score >= RULES_YES_THRESHOLD:
        classification = "yes"
    elif score <= RULES_NO_THRESHOLD:
        classification = "no"
    else:
        classification = "maybe"
    
    return {
        'score': round(score, 2),
        'classification': classification,
        'reasons': reasons
    }
```

### LLM Curator (llm_curator.py)

```python
def run_llm_curation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process MAYBE records through LLM for nuanced classification.
    Updates DataFrame with llm_score, llm_reason, final_score, final_classification.
    """
    # Filter to MAYBE records only
    maybe_df = df[df['rules_classification'] == 'maybe'].copy()
    
    # Process in batches
    for batch in batches:
        accounts_text = format_accounts_for_prompt(batch)
        results = call_deepseek_api(accounts_text)
        
        # Map results back to DataFrame
        for username, result in results.items():
            df.loc[df['username'] == username, 'llm_score'] = result['score']
            df.loc[df['username'] == username, 'llm_reason'] = result['reason']
    
    # Compute final classification
    df['final_score'] = df.apply(lambda row: 
        row['llm_score'] if row['rules_classification'] == 'maybe' 
        else row['rules_score'], axis=1)
    
    df['final_classification'] = df.apply(lambda row:
        'yes' if row['final_score'] >= FINAL_INCLUSION_THRESHOLD 
        else 'no', axis=1)
    
    return df
```

### Configuration (config.py)

```python
# Rules Engine Thresholds
MIN_FOLLOWERS = 200
MAX_FOLLOWERS = 500_000
BIG_BRAND_FOLLOWER_THRESHOLD = 100_000
MAX_FOLLOWING_RATIO = 5.0

RULES_YES_THRESHOLD = 0.70   # Above this → auto-YES (skip LLM)
RULES_NO_THRESHOLD = 0.25    # Below this → auto-NO (skip LLM)
FINAL_INCLUSION_THRESHOLD = 0.55  # After LLM scoring

# Strong positive signals — handmade/unique/creative small businesses
STRONG_YES_KEYWORDS = [
    "handmade", "hand made", "hand-made", "handcrafted",
    "one of a kind", "ooak", "one-of-a-kind",
    "small batch", "made to order", "custom order",
    "artist", "artisan", "maker", "creator", "designer",
    "fiber art", "wearable art", "functional art",
    "psychedelic", "trippy", "tie dye",
    "festival wear", "festival fashion", "festival clothing",
    # [... more ...]
]

# Strong negative signals — big brands, mass production, personal accounts
STRONG_NO_KEYWORDS = [
    "shipping worldwide", "worldwide shipping",
    "influencer", "content creator", "youtuber",
    "dj", "producer", "music producer", "singer",
    "speaker", "motivational speaker", "spiritual leader",
    "tattoo", "yoga", "photographer",
    # [... more ...]
]
```

---

## Test Cases for Validation

After implementing fixes, re-test these accounts:

1. **go.with.the.bo** — Should be NO (influencer with affiliate link)
2. **etudemesf** — Should be NO (high fashion, not festival)
3. **_sewciopath__** — Should be MAYBE or NO (no shop link)
4. **[event promotion group]** — Should be NO (events, not products)
5. **[personal raver account]** — Should be NO (personal, not vendor)

**Expected outcomes after fixes:**
- False positive rate: < 5% (currently ~10-15% estimated)
- Shop URL requirement: 95%+ of approved vendors
- Aesthetic accuracy: High fashion excluded, festival fashion included

---

## Next Steps

1. **Opus reviews this document** and provides recommendations
2. **Implement agreed-upon fixes** to rules_engine.py, llm_curator.py, config.py
3. **Re-run pipeline** on full 1,965 records
4. **Manual validation** of 50-100 random approved vendors
5. **Iterate** based on new findings

---

*Document prepared by Bub for Opus audit — 2026-02-12*
