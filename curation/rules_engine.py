"""
Rules Engine: Fast deterministic classification of scraped Instagram accounts.

Assigns each record a score (0.0 - 1.0) and a classification:
  - "yes"   (score >= YES_THRESHOLD)  → confident match, skip LLM
  - "no"    (score <= NO_THRESHOLD)   → confident reject, skip LLM
  - "maybe" (between thresholds)      → ambiguous, send to LLM

The goal is to classify ~70% of records here cheaply, leaving only ~30%
for the more expensive LLM pass.
"""
import pandas as pd
import re
from .config import (
    MIN_FOLLOWERS, MAX_FOLLOWERS, BIG_BRAND_FOLLOWER_THRESHOLD,
    MAX_FOLLOWING_RATIO,
    RULES_YES_THRESHOLD, RULES_NO_THRESHOLD,
    STRONG_YES_KEYWORDS, WEAK_YES_KEYWORDS, STRONG_NO_KEYWORDS,
    BIG_BRAND_DOMAINS, SHOP_URL_PATTERNS,
)


def _count_keyword_matches(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear in text (case-insensitive)."""
    if not text:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def _has_shop_url(url: str) -> bool:
    """Check if external URL looks like an actual shop."""
    if not url:
        return False
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in SHOP_URL_PATTERNS)


def _is_known_big_brand(domain: str) -> bool:
    """Check if domain is a known big brand."""
    if not domain:
        return False
    return domain.lower() in BIG_BRAND_DOMAINS


def _is_personal_account(row: pd.Series) -> bool:
    """
    Heuristic: account is likely a personal (non-vendor) account.
    Personal accounts have no shop URL, no business flag, high following ratio,
    and bio is about personal life rather than products.
    """
    # No external URL at all
    no_url = not row.get('external_url', '')

    # Not a business account
    not_business = not row.get('is_business', False)

    # High following-to-follower ratio (follows way more than followers)
    followers = row.get('followers', 0)
    following = row.get('following', 0)
    high_ratio = (following / max(followers, 1)) > MAX_FOLLOWING_RATIO

    # Bio has zero vendor-like keywords
    all_text = row.get('all_text', '')
    has_any_positive = _count_keyword_matches(all_text, STRONG_YES_KEYWORDS + WEAK_YES_KEYWORDS) > 0

    return no_url and not_business and high_ratio and not has_any_positive


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

    # =========================================================================
    # INSTANT DISQUALIFIERS (→ score 0)
    # =========================================================================

    # Known big brand domain
    if _is_known_big_brand(domain):
        return {
            'score': 0.0,
            'classification': 'no',
            'reasons': [f'known big brand domain: {domain}']
        }

    # Too many followers — almost certainly a big brand
    if followers > BIG_BRAND_FOLLOWER_THRESHOLD:
        return {
            'score': 0.05,
            'classification': 'no',
            'reasons': [f'followers ({followers:,}) exceed big brand threshold']
        }

    # Too few followers — not an established vendor
    if followers < MIN_FOLLOWERS:
        return {
            'score': 0.1,
            'classification': 'no',
            'reasons': [f'followers ({followers:,}) below minimum ({MIN_FOLLOWERS})']
        }

    # No bio and no URL — can't evaluate
    if not all_text.strip(' |') and not external_url:
        return {
            'score': 0.05,
            'classification': 'no',
            'reasons': ['no bio, no URL — insufficient data']
        }

    # No external URL + not a business account + no vendor keywords = likely personal
    if (not external_url and
        not row.get('is_business', False) and
        _count_keyword_matches(all_text, STRONG_YES_KEYWORDS) == 0):
        # Check if they have ANY weak positive signals at all
        weak_count = _count_keyword_matches(all_text, WEAK_YES_KEYWORDS)
        if weak_count == 0:
            return {
                'score': 0.12,
                'classification': 'no',
                'reasons': ['no URL, not business, no vendor keywords — likely personal account']
            }

    # Likely personal account
    if _is_personal_account(row):
        return {
            'score': 0.1,
            'classification': 'no',
            'reasons': ['personal account pattern (no URL, not business, high follow ratio, no vendor keywords)']
        }

    # =========================================================================
    # SCORING SIGNALS
    # =========================================================================

    # Strong positive keywords (each worth +0.08, capped)
    strong_yes_count = _count_keyword_matches(all_text, STRONG_YES_KEYWORDS)
    if strong_yes_count > 0:
        boost = min(strong_yes_count * 0.08, 0.35)
        score += boost
        reasons.append(f'+{boost:.2f} strong positive keywords ({strong_yes_count} matches)')

    # Weak positive keywords (each worth +0.03, capped)
    weak_yes_count = _count_keyword_matches(all_text, WEAK_YES_KEYWORDS)
    if weak_yes_count > 0:
        boost = min(weak_yes_count * 0.03, 0.15)
        score += boost
        reasons.append(f'+{boost:.2f} weak positive keywords ({weak_yes_count} matches)')

    # Strong negative keywords (each worth -0.12, capped)
    strong_no_count = _count_keyword_matches(all_text, STRONG_NO_KEYWORDS)
    if strong_no_count > 0:
        penalty = min(strong_no_count * 0.12, 0.40)
        score -= penalty
        reasons.append(f'-{penalty:.2f} negative keywords ({strong_no_count} matches)')

    # Has a shop URL pattern (+0.15)
    if _has_shop_url(external_url):
        score += 0.15
        reasons.append('+0.15 shop URL pattern detected')

    # Is a business account (+0.08)
    if row.get('is_business', False):
        score += 0.08
        reasons.append('+0.08 business account flag')

    # Has any external URL (+0.05)
    if external_url:
        score += 0.05
        reasons.append('+0.05 has external URL')

    # Etsy/BigCartel/handmade marketplace URL (+0.15)
    if domain and any(m in domain for m in ['etsy.com', 'bigcartel.com', 'storenvy.com']):
        score += 0.15
        reasons.append('+0.15 handmade marketplace URL')

    # Follower sweet spot (1K-50K is ideal for small businesses)
    if 1000 <= followers <= 50000:
        score += 0.05
        reasons.append('+0.05 follower count in small business sweet spot')
    elif followers > MAX_FOLLOWERS:
        score -= 0.15
        reasons.append(f'-0.15 very high followers ({followers:,})')

    # "Shipping worldwide" + high followers = big brand pattern
    if 'shipping worldwide' in all_text and followers > 50000:
        score -= 0.20
        reasons.append('-0.20 big brand shipping pattern')

    # Linktr.ee or similar aggregators — neutral but slightly positive
    # (means they have something to link to)
    if domain and any(lt in domain for lt in ['linktr.ee', 'linkin.bio', 'linkr.bio', 'hihello.com']):
        score += 0.02
        reasons.append('+0.02 has link aggregator')

    # =========================================================================
    # CLAMP AND CLASSIFY
    # =========================================================================
    score = max(0.0, min(1.0, score))

    if score >= RULES_YES_THRESHOLD:
        classification = 'yes'
    elif score <= RULES_NO_THRESHOLD:
        classification = 'no'
    else:
        classification = 'maybe'

    return {
        'score': round(score, 3),
        'classification': classification,
        'reasons': reasons
    }


def run_rules_engine(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply rules engine to entire DataFrame.
    Adds columns: rules_score, rules_classification, rules_reasons
    """
    results = df.apply(score_record, axis=1, result_type='expand')

    df = df.copy()
    df['rules_score'] = results['score']
    df['rules_classification'] = results['classification']
    df['rules_reasons'] = results['reasons']

    # Stats
    counts = df['rules_classification'].value_counts()
    total = len(df)
    print(f"\n[rules_engine] Classification results ({total} records):")
    for cls in ['yes', 'no', 'maybe']:
        n = counts.get(cls, 0)
        print(f"  {cls:>5}: {n:>6} ({n/total*100:.1f}%)")

    determined = counts.get('yes', 0) + counts.get('no', 0)
    print(f"  Determined by rules: {determined/total*100:.1f}%")
    print(f"  Needs LLM: {counts.get('maybe', 0)} records")

    return df


if __name__ == "__main__":
    import sys
    from .data_loader import load_data

    if len(sys.argv) < 2:
        print("Usage: python -m curation.rules_engine <path_to_csv>")
        sys.exit(1)

    df = load_data(sys.argv[1])
    df = run_rules_engine(df)

    # Show some examples of each classification
    for cls in ['yes', 'no', 'maybe']:
        subset = df[df['rules_classification'] == cls].head(3)
        print(f"\n--- {cls.upper()} examples ---")
        for _, row in subset.iterrows():
            print(f"  @{row['username']} (followers: {row['followers']:,}, "
                  f"score: {row['rules_score']:.2f})")
            print(f"    Bio: {row['biography'][:80]}...")
            print(f"    Reasons: {row['rules_reasons']}")

    # Save intermediate output
    output_path = "output/rules_output.csv"
    import os
    os.makedirs("output", exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nSaved to {output_path}")
