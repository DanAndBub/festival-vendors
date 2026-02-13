"""
Rules Engine v2: Pre-filter that ONLY rejects obvious NOs.

V2 PHILOSOPHY: Rules engine is a bouncer, not a judge.
- It throws out the trash (personal accounts, big brands, empty profiles)
- Everything else goes to the LLM for real evaluation
- NO auto-YES anymore. Period.

Output classifications:
  - "no"     → confident reject, skip LLM
  - "review" → send to LLM for scoring

Also computes a "signal strength" score that helps the LLM:
  - product_signals: count of product/making keywords
  - aesthetic_signals: count of trippy/festival keywords
  - negative_signals: count of disqualifying keywords
  - has_shop_url: boolean
  - url_type: "shop" | "aggregator" | "non_shop" | "own_domain" | "none"
"""
import pandas as pd
import re
from .config import (
    MIN_FOLLOWERS, MAX_FOLLOWERS, BIG_BRAND_FOLLOWER_THRESHOLD,
    RULES_NO_THRESHOLD,
    PRODUCT_KEYWORDS, AESTHETIC_KEYWORDS, NEGATIVE_KEYWORDS,
    PERSONAL_ACCOUNT_SIGNALS,
    BIG_BRAND_DOMAINS, NON_SHOP_DOMAINS, SHOP_DOMAINS,
    SHOP_URL_PATTERNS, LINK_AGGREGATOR_DOMAINS,
)


def _count_keyword_matches(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    """Count keyword matches, return count and which keywords matched."""
    if not text:
        return 0, []
    text_lower = text.lower()
    matched = [kw for kw in keywords if kw.lower() in text_lower]
    return len(matched), matched


def _classify_url(url: str, domain: str) -> str:
    """
    Classify a URL into: shop | aggregator | non_shop | own_domain | none
    This is critical — v1 treated all URLs the same, which was wrong.
    """
    if not url or not url.strip():
        return "none"

    domain_lower = (domain or "").lower().strip()
    url_lower = url.lower()

    # Check known non-shop domains first (tickets, social media, payment)
    for nsd in NON_SHOP_DOMAINS:
        if nsd in domain_lower:
            return "non_shop"

    # Check known shop domains
    for sd in SHOP_DOMAINS:
        if sd in domain_lower:
            return "shop"

    # Check link aggregators
    for la in LINK_AGGREGATOR_DOMAINS:
        if la in domain_lower:
            return "aggregator"

    # Check URL patterns that suggest a shop
    for pattern in SHOP_URL_PATTERNS:
        if pattern in url_lower:
            return "shop"

    # Known big brand
    if domain_lower in BIG_BRAND_DOMAINS:
        return "non_shop"

    # Has their own domain — likely a real business
    if domain_lower and '.' in domain_lower:
        return "own_domain"

    return "own_domain"  # fallback if URL exists


def score_record(row: pd.Series) -> dict:
    """
    Score a single record. Returns:
      - classification: "no" or "review"
      - score: 0.0-1.0 (signal strength, NOT a final judgment)
      - reasons: list of explanation strings
      - signals: dict of structured signals for LLM context
    """
    all_text = row.get('all_text', '')
    bio = str(row.get('biography', '')).lower()
    followers = row.get('followers', 0)
    following = row.get('following', 0)
    domain = str(row.get('domain', '')).strip()
    external_url = str(row.get('external_url', '')).strip()
    is_business = row.get('is_business', False)

    reasons = []

    # Classify URL type
    url_type = _classify_url(external_url, domain)

    # Count signal types
    product_count, product_matched = _count_keyword_matches(all_text, PRODUCT_KEYWORDS)
    aesthetic_count, aesthetic_matched = _count_keyword_matches(all_text, AESTHETIC_KEYWORDS)
    negative_count, negative_matched = _count_keyword_matches(all_text, NEGATIVE_KEYWORDS)
    personal_count, personal_matched = _count_keyword_matches(all_text, PERSONAL_ACCOUNT_SIGNALS)

    # Build signals dict (passed to LLM as context)
    signals = {
        'product_signals': product_count,
        'aesthetic_signals': aesthetic_count,
        'negative_signals': negative_count,
        'personal_signals': personal_count,
        'url_type': url_type,
        'is_business': bool(is_business),
        'product_keywords': product_matched[:5],  # Top 5 for LLM context
        'aesthetic_keywords': aesthetic_matched[:5],
        'negative_keywords': negative_matched[:5],
    }

    # =========================================================================
    # INSTANT REJECT — these never go to LLM
    # =========================================================================

    # Known big brand domain
    if domain.lower() in BIG_BRAND_DOMAINS:
        return {
            'score': 0.0, 'classification': 'no',
            'reasons': [f'known big brand: {domain}'],
            'signals': signals,
        }

    # Way too many followers
    if followers > BIG_BRAND_FOLLOWER_THRESHOLD:
        return {
            'score': 0.0, 'classification': 'no',
            'reasons': [f'followers ({followers:,}) exceed brand threshold ({BIG_BRAND_FOLLOWER_THRESHOLD:,})'],
            'signals': signals,
        }

    # Too few followers
    if followers < MIN_FOLLOWERS:
        return {
            'score': 0.05, 'classification': 'no',
            'reasons': [f'followers ({followers:,}) below minimum ({MIN_FOLLOWERS})'],
            'signals': signals,
        }

    # Completely empty — no bio, no URL, nothing to evaluate
    text_content = all_text.replace('|', '').strip()
    if not text_content and not external_url:
        return {
            'score': 0.0, 'classification': 'no',
            'reasons': ['no bio and no URL — nothing to evaluate'],
            'signals': signals,
        }

    # No URL + not business + no product keywords + no aesthetic keywords
    # = almost certainly a personal account
    if (url_type == "none" and not is_business
        and product_count == 0 and aesthetic_count == 0):
        return {
            'score': 0.05, 'classification': 'no',
            'reasons': ['personal account (no URL, not business, no product/aesthetic signals)'],
            'signals': signals,
        }

    # Strong personal account signals + no product signals
    if personal_count > 0 and product_count == 0:
        return {
            'score': 0.10, 'classification': 'no',
            'reasons': [f'personal account signals ({personal_matched}) with no product keywords'],
            'signals': signals,
        }

    # Only a non-shop URL (YouTube, Venmo, tickets) + no product signals
    if url_type == "non_shop" and product_count == 0:
        return {
            'score': 0.10, 'classification': 'no',
            'reasons': [f'non-shop URL ({domain}) with no product keywords'],
            'signals': signals,
        }

    # Heavy negative signals with no positive signals
    if negative_count >= 2 and product_count == 0 and aesthetic_count == 0:
        return {
            'score': 0.10, 'classification': 'no',
            'reasons': [f'multiple negative signals ({negative_matched}) with no positives'],
            'signals': signals,
        }

    # =========================================================================
    # SCORING — for LLM prioritization, NOT for auto-approval
    # =========================================================================
    score = 0.3  # Base score (survived rejection)

    # Product signals are the strongest positive
    if product_count > 0:
        score += min(product_count * 0.06, 0.25)
        reasons.append(f'+product signals: {product_matched[:3]}')

    # Aesthetic signals
    if aesthetic_count > 0:
        score += min(aesthetic_count * 0.04, 0.15)
        reasons.append(f'+aesthetic signals: {aesthetic_matched[:3]}')

    # URL type scoring
    if url_type == "shop":
        score += 0.15
        reasons.append(f'+shop URL ({domain})')
    elif url_type == "own_domain":
        score += 0.10
        reasons.append(f'+own domain ({domain})')
    elif url_type == "aggregator":
        score += 0.05
        reasons.append(f'+link aggregator ({domain})')
    elif url_type == "non_shop":
        score -= 0.10
        reasons.append(f'-non-shop URL ({domain})')

    # Business account
    if is_business:
        score += 0.05
        reasons.append('+business account')

    # Negative keywords
    if negative_count > 0:
        score -= min(negative_count * 0.08, 0.25)
        reasons.append(f'-negative: {negative_matched[:3]}')

    # Clamp
    score = max(0.0, min(1.0, score))

    # Final classification: NO or REVIEW
    if score < RULES_NO_THRESHOLD:
        classification = 'no'
    else:
        classification = 'review'

    return {
        'score': round(score, 3),
        'classification': classification,
        'reasons': reasons,
        'signals': signals,
    }


def run_rules_engine(df: pd.DataFrame) -> pd.DataFrame:
    """Apply rules engine to entire DataFrame."""
    results = []
    for _, row in df.iterrows():
        results.append(score_record(row))

    df = df.copy()
    df['rules_score'] = [r['score'] for r in results]
    df['rules_classification'] = [r['classification'] for r in results]
    df['rules_reasons'] = [r['reasons'] for r in results]
    df['signals'] = [r['signals'] for r in results]

    # Stats
    counts = df['rules_classification'].value_counts()
    total = len(df)
    print(f"\n[rules_engine v2] Results ({total} records):")
    for cls in ['review', 'no']:
        n = counts.get(cls, 0)
        print(f"  {cls:>6}: {n:>6} ({n/total*100:.1f}%)")
    print(f"  Rejected by rules: {counts.get('no', 0)}")
    print(f"  Sent to LLM: {counts.get('review', 0)}")

    return df


if __name__ == "__main__":
    import sys
    from .data_loader import load_data

    if len(sys.argv) < 2:
        print("Usage: python -m curation.rules_engine <path_to_csv>")
        sys.exit(1)

    df = load_data(sys.argv[1])
    df = run_rules_engine(df)
