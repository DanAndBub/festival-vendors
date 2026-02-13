"""
LLM Curator v2: The real judge. Every potential vendor goes through here.

V2 CHANGES:
1. Prompt completely rewritten with real YES/NO examples from the audit
2. LLM receives structured signals from rules engine as context
3. LLM must answer 3 specific questions (not just one score)
4. Higher threshold (0.70 vs 0.55)
5. Smaller batch size (5 vs 10) for better per-record accuracy
6. Post-LLM validation gate: shop URL required regardless of score
"""
import json
import os
import time
import requests
import pandas as pd
from .config import (
    DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL,
    LLM_BATCH_SIZE, LLM_MAX_RETRIES, LLM_RETRY_DELAY, LLM_TIMEOUT,
    LLM_YES_THRESHOLD, PROGRESS_FILE,
    REQUIRE_SHOP_URL, NON_SHOP_DOMAINS,
)

SYSTEM_PROMPT = """You are a strict curator for a HANDMADE TRIPPY FESTIVAL VENDOR directory. You are the final gatekeeper. Only approve vendors you'd personally recommend to someone looking for unique, one-of-a-kind festival gear.

For each account, answer THREE questions:
1. SELLS PRODUCTS? Does this account sell tangible products (not services, events, or content)?
2. HAS SHOP? Is there a way to buy from them (shop URL, Etsy, marketplace, "DM for orders")?
3. FESTIVAL AESTHETIC? Is their style trippy, psychedelic, bohemian, rave, colorful, or uniquely creative? (NOT generic fashion, high fashion, or mass-produced)

SCORING GUIDE:
0.85-1.0: Perfect fit. Handmade + trippy/unique + clear shop. Examples: handmade beaded rave accessories, psychedelic tie-dye clothing, one-of-a-kind resin art, custom festival harnesses.
0.70-0.84: Good fit. Sells creative products, has a shop, festival-adjacent aesthetic.
0.50-0.69: Borderline. Missing one of: shop link, aesthetic fit, or unclear if they sell.
0.20-0.49: Probably not. Influencer, personal account, wrong aesthetic, or no products.
0.00-0.19: Definitely not. DJ, photographer, event promoter, big brand, personal account.

CRITICAL RULES — these override everything:
- NO SHOP/BUY PATH = max score 0.50 (even if everything else is perfect)
- Influencer/affiliate accounts (promote others' products) = max score 0.20
- Personal raver accounts (attend festivals, don't sell) = max score 0.15
- Event organizers/promoters (even with merch) = max score 0.30
- "Slow fashion" / "minimalist" / high fashion designers = max score 0.40 (wrong aesthetic)
- Photographers, DJs, performers, service providers = max score 0.15

RESPOND WITH ONLY A JSON ARRAY. No markdown, no explanation outside JSON."""

USER_PROMPT_TEMPLATE = """Score these accounts for the festival vendor directory.

Return JSON array:
[{{"username": "x", "sells_products": true/false, "has_shop": true/false, "festival_aesthetic": true/false, "score": 0.0-1.0, "reason": "brief explanation"}}]

Accounts:
{accounts_text}

JSON:"""


def _format_account_for_prompt(row: pd.Series) -> str:
    """Format account data with structured signals for LLM."""
    parts = [f"@{row['username']}"]

    followers = row.get('followers', 0)
    if followers:
        parts.append(f"({int(followers):,} followers)")

    # Include signal analysis from rules engine
    signals = row.get('signals', {})
    if isinstance(signals, str):
        try:
            signals = json.loads(signals.replace("'", '"'))
        except:
            signals = {}

    if signals.get('is_business'):
        parts.append("[business account]")

    url_type = signals.get('url_type', 'none')
    parts.append(f"[URL: {url_type}]")

    bio = str(row.get('biography', '')).strip()
    if bio:
        parts.append(f'Bio: "{bio[:250]}"')

    url = str(row.get('external_url', '')).strip()
    if url and url != 'nan':
        domain = str(row.get('domain', '')).strip()
        parts.append(f"Link: {domain or url[:60]}")

    desc = str(row.get('website_description', '')).strip()
    if desc and desc not in ('', '|', 'nan'):
        parts.append(f'Site desc: "{desc[:150]}"')

    title = str(row.get('website_title', '')).strip()
    if title and title not in ('', 'nan'):
        parts.append(f'Site title: "{title[:80]}"')

    # Signal summary for LLM
    if signals.get('product_keywords'):
        parts.append(f"Product signals: {signals['product_keywords']}")
    if signals.get('negative_keywords'):
        parts.append(f"Warning signals: {signals['negative_keywords']}")

    return ' | '.join(parts)


def _call_deepseek(accounts_text: str) -> list[dict]:
    """Make API call to DeepSeek."""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY not set in .env")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(accounts_text=accounts_text)},
        ],
        "temperature": 0.05,  # Very low — we want consistent, conservative scoring
        "max_tokens": 2000,
    }

    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=LLM_TIMEOUT,
            )
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content'].strip()

            # Strip markdown fences
            if content.startswith('```'):
                content = content.split('\n', 1)[1] if '\n' in content else content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

            results = json.loads(content)
            return results if isinstance(results, list) else [results]

        except requests.exceptions.RequestException as e:
            print(f"  [llm] API error (attempt {attempt+1}/{LLM_MAX_RETRIES}): {e}")
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(LLM_RETRY_DELAY * (2 ** attempt))
            else:
                raise
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  [llm] Parse error (attempt {attempt+1}): {e}")
            print(f"  [llm] Raw content: {content[:200]}")
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(LLM_RETRY_DELAY)
            else:
                return []


def _load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"scored_usernames": {}}


def _save_progress(progress: dict):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)


def _has_real_shop_url(row: pd.Series) -> bool:
    """Check if the account has a real shop URL (not tickets, social media, etc)."""
    signals = row.get('signals', {})
    if isinstance(signals, str):
        try:
            signals = json.loads(signals.replace("'", '"'))
        except:
            signals = {}

    url_type = signals.get('url_type', 'none')

    # These count as having a shop
    if url_type in ('shop', 'own_domain'):
        return True

    # Aggregators MIGHT link to a shop — we'll allow them if LLM is confident
    if url_type == 'aggregator':
        return True

    # Bio says "DM for orders/custom" counts as a purchase path
    bio = str(row.get('biography', '')).lower()
    dm_patterns = ['dm for orders', 'dm for custom', 'dm for pricing',
                   'dm to order', 'dm to purchase', 'message for orders',
                   'message for custom', 'message to order']
    if any(p in bio for p in dm_patterns):
        return True

    return False


def run_llm_curation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Send all REVIEW records through LLM, then apply validation gate.
    """
    df = df.copy()
    df['llm_score'] = pd.NA
    df['llm_reason'] = ''
    df['sells_products'] = pd.NA
    df['has_shop'] = pd.NA
    df['festival_aesthetic'] = pd.NA
    df['final_score'] = 0.0
    df['final_classification'] = 'no'

    # Set NO records
    no_mask = df['rules_classification'] == 'no'
    df.loc[no_mask, 'final_score'] = df.loc[no_mask, 'rules_score']
    df.loc[no_mask, 'final_classification'] = 'no'

    # Process REVIEW records
    review_mask = df['rules_classification'] == 'review'
    review_df = df[review_mask]

    if len(review_df) == 0:
        print("[llm_curator v2] No records to review")
        return df

    print(f"[llm_curator v2] Sending {len(review_df)} records to DeepSeek...")

    # Load progress
    progress = _load_progress()
    scored = progress.get("scored_usernames", {})

    to_process = review_df[~review_df['username'].isin(scored)]
    if len(review_df) - len(to_process) > 0:
        print(f"  Resuming: {len(review_df) - len(to_process)} cached, {len(to_process)} remaining")

    # Apply cached scores
    for username, data in scored.items():
        mask = df['username'] == username
        if mask.any():
            df.loc[mask, 'llm_score'] = data.get('score', 0)
            df.loc[mask, 'llm_reason'] = data.get('reason', '')
            df.loc[mask, 'sells_products'] = data.get('sells_products')
            df.loc[mask, 'has_shop'] = data.get('has_shop')
            df.loc[mask, 'festival_aesthetic'] = data.get('festival_aesthetic')

    # Process in batches
    batches = [to_process.iloc[i:i+LLM_BATCH_SIZE] for i in range(0, len(to_process), LLM_BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        print(f"  Batch {batch_idx+1}/{len(batches)} ({len(batch)} records)...")

        accounts_text = "\n".join(
            f"{i+1}. {_format_account_for_prompt(row)}"
            for i, (_, row) in enumerate(batch.iterrows())
        )

        try:
            results = _call_deepseek(accounts_text)
        except Exception as e:
            print(f"  Batch {batch_idx+1} FAILED: {e}")
            continue

        result_map = {}
        for r in results:
            uname = r.get('username', '').lower().lstrip('@')
            result_map[uname] = r

        for _, row in batch.iterrows():
            username = row['username']
            r = result_map.get(username, {})

            llm_score = float(r.get('score', 0.3))
            llm_reason = r.get('reason', 'not returned by LLM')
            sells = r.get('sells_products', False)
            has_shop = r.get('has_shop', False)
            aesthetic = r.get('festival_aesthetic', False)

            mask = df['username'] == username
            df.loc[mask, 'llm_score'] = llm_score
            df.loc[mask, 'llm_reason'] = llm_reason
            df.loc[mask, 'sells_products'] = sells
            df.loc[mask, 'has_shop'] = has_shop
            df.loc[mask, 'festival_aesthetic'] = aesthetic

            scored[username] = {
                'score': llm_score, 'reason': llm_reason,
                'sells_products': sells, 'has_shop': has_shop,
                'festival_aesthetic': aesthetic,
            }

        progress["scored_usernames"] = scored
        _save_progress(progress)

        if batch_idx < len(batches) - 1:
            time.sleep(1)

    # =========================================================================
    # VALIDATION GATE — hard requirements AFTER LLM scoring
    # =========================================================================
    print(f"\n[validation gate] Applying hard requirements...")
    gate_rejections = {'no_shop': 0, 'low_score': 0, 'no_products': 0, 'non_shop_url': 0}

    for idx, row in df.iterrows():
        if row['rules_classification'] == 'no':
            continue  # Already rejected

        llm_score = row.get('llm_score', 0) or 0

        # Gate 1: LLM score must meet threshold
        if llm_score < LLM_YES_THRESHOLD:
            df.at[idx, 'final_score'] = float(llm_score)
            df.at[idx, 'final_classification'] = 'no'
            gate_rejections['low_score'] += 1
            continue

        # Gate 2: Must have a real shop URL
        if REQUIRE_SHOP_URL and not _has_real_shop_url(row):
            df.at[idx, 'final_score'] = float(llm_score)
            df.at[idx, 'final_classification'] = 'no'
            df.at[idx, 'llm_reason'] = (row.get('llm_reason', '') + ' | GATE: rejected, no shop URL').strip(' |')
            gate_rejections['no_shop'] += 1
            continue

        # Gate 3: LLM must confirm sells_products=true
        if row.get('sells_products') == False:
            df.at[idx, 'final_score'] = float(llm_score)
            df.at[idx, 'final_classification'] = 'no'
            gate_rejections['no_products'] += 1
            continue

        # Gate 4: If URL is non-shop domain, reject regardless
        signals = row.get('signals', {})
        if isinstance(signals, str):
            try:
                signals = json.loads(signals.replace("'", '"'))
            except:
                signals = {}
        if signals.get('url_type') == 'non_shop':
            df.at[idx, 'final_score'] = float(llm_score)
            df.at[idx, 'final_classification'] = 'no'
            gate_rejections['non_shop_url'] += 1
            continue

        # PASSED ALL GATES
        df.at[idx, 'final_score'] = float(llm_score)
        df.at[idx, 'final_classification'] = 'yes'

    # Stats
    final_yes = (df['final_classification'] == 'yes').sum()
    total_review = review_mask.sum()
    print(f"\n[llm_curator v2] Final results:")
    print(f"  LLM reviewed: {total_review}")
    print(f"  Gate rejections: {gate_rejections}")
    print(f"  Final YES: {final_yes}")
    print(f"  Final NO: {(df['final_classification'] == 'no').sum()}")

    return df


if __name__ == "__main__":
    print("Run via: python -m curation.run_pipeline --input <csv> --output output/")
