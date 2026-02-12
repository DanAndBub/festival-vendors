"""
LLM Curator: Send ambiguous ("maybe") records to DeepSeek for nuanced classification.

Features:
  - Batches multiple records per API call (saves tokens/cost)
  - Resumable: saves progress after each batch
  - Retry with backoff on API errors
  - Parses structured JSON responses
"""
import json
import os
import time
import requests
import pandas as pd
from .config import (
    DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL,
    LLM_BATCH_SIZE, LLM_MAX_RETRIES, LLM_RETRY_DELAY, LLM_TIMEOUT,
    FINAL_INCLUSION_THRESHOLD, PROGRESS_FILE,
)

# System prompt that teaches DeepSeek the curation criteria
SYSTEM_PROMPT = """You are a festival vendor curator. Your job is to evaluate Instagram accounts and determine if they are SMALL, INDEPENDENT, HANDMADE/CREATIVE vendors that would be a good fit for a psychedelic/festival vendor directory.

IDEAL VENDORS (score 0.7-1.0):
- Handmade, one-of-a-kind products (clothing, jewelry, art, toys, decor)
- Small batch, artisan-crafted items
- Psychedelic, trippy, colorful, unique aesthetic
- Independent creators/makers (not resellers)
- Festival-oriented products that are genuinely creative
- Etsy shops, small Shopify stores, independent artists

REJECT (score 0.0-0.3):
- Big brands or mass-produced "rave wear" companies
- Drop-shipping or wholesale resellers
- Generic fast fashion marketed as "festival" wear
- Personal accounts (not selling anything)
- Photographers, DJs, promoters, service providers (not product vendors)
- Accounts with no clear product offering

BORDERLINE (score 0.3-0.7):
- Small businesses that sell festival-adjacent items but aren't particularly unique
- Artists who may sell prints but it's unclear from their bio
- Accounts that seem creative but have limited information

For each account, return a score from 0.0 to 1.0 and a brief reason.

IMPORTANT: Respond ONLY with valid JSON. No markdown, no extra text."""

USER_PROMPT_TEMPLATE = """Evaluate these Instagram accounts for our festival vendor directory.

For each account, return a JSON array with objects containing:
- "username": the account username
- "score": float 0.0-1.0
- "reason": brief explanation (under 20 words)

Accounts to evaluate:
{accounts_text}

Respond with ONLY a JSON array. Example format:
[{{"username": "example", "score": 0.85, "reason": "Handmade beaded jewelry, clearly artisan-crafted"}}]"""


def _format_account_for_prompt(row: pd.Series) -> str:
    """Format a single account's data for the LLM prompt."""
    parts = [f"@{row['username']}"]

    if row.get('followers', 0) > 0:
        parts.append(f"({row['followers']:,} followers)")

    if row.get('is_business'):
        parts.append("[business account]")

    bio = row.get('biography', '').strip()
    if bio:
        # Truncate long bios to save tokens
        parts.append(f"Bio: \"{bio[:200]}\"")

    url = row.get('external_url', '').strip()
    if url:
        parts.append(f"URL: {url}")

    desc = row.get('website_description', '').strip()
    if desc and desc != '|':
        parts.append(f"Site: \"{desc[:150]}\"")

    return ' | '.join(parts)


def _call_deepseek(accounts_text: str) -> list[dict]:
    """Make a single API call to DeepSeek and parse the response."""
    if not DEEPSEEK_API_KEY:
        raise ValueError(
            "DEEPSEEK_API_KEY not set. Add it to .env file."
        )

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                accounts_text=accounts_text
            )},
        ],
        "temperature": 0.1,  # Low temp for consistent scoring
        "max_tokens": 2000,
    }

    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = requests.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT,
            )
            response.raise_for_status()

            content = response.json()['choices'][0]['message']['content'].strip()

            # Strip markdown code fences if present
            if content.startswith('```'):
                content = content.split('\n', 1)[1] if '\n' in content else content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

            # Parse JSON
            results = json.loads(content)

            if isinstance(results, list):
                return results
            elif isinstance(results, dict):
                return [results]
            else:
                raise ValueError(f"Unexpected response format: {type(results)}")

        except requests.exceptions.RequestException as e:
            print(f"  [llm] API error (attempt {attempt+1}/{LLM_MAX_RETRIES}): {e}")
            if attempt < LLM_MAX_RETRIES - 1:
                wait = LLM_RETRY_DELAY * (2 ** attempt)
                print(f"  [llm] Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  [llm] Parse error (attempt {attempt+1}/{LLM_MAX_RETRIES}): {e}")
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(LLM_RETRY_DELAY)
            else:
                # Return empty scores — will be treated as "no" by default
                print(f"  [llm] Failed to parse after {LLM_MAX_RETRIES} attempts")
                return []


def _load_progress() -> dict:
    """Load progress from disk for resume capability."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"scored_usernames": {}}


def _save_progress(progress: dict):
    """Save progress to disk."""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)


def run_llm_curation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Send 'maybe' records to DeepSeek for scoring.
    Updates the DataFrame with llm_score and llm_reason columns.
    Combines with rules_score for final_score.
    """
    df = df.copy()
    df['llm_score'] = None
    df['llm_reason'] = ''
    df['final_score'] = df['rules_score']
    df['final_classification'] = df['rules_classification']

    # Only process "maybe" records
    maybe_mask = df['rules_classification'] == 'maybe'
    maybe_df = df[maybe_mask]

    if len(maybe_df) == 0:
        print("[llm_curator] No 'maybe' records to process")
        return df

    print(f"[llm_curator] Processing {len(maybe_df)} 'maybe' records with DeepSeek...")

    # Load progress for resume
    progress = _load_progress()
    scored = progress.get("scored_usernames", {})

    # Filter out already-scored usernames
    to_process = maybe_df[~maybe_df['username'].isin(scored)]
    already_done = len(maybe_df) - len(to_process)
    if already_done > 0:
        print(f"[llm_curator] Resuming: {already_done} already scored, {len(to_process)} remaining")

    # Apply cached scores
    for username, data in scored.items():
        mask = df['username'] == username
        if mask.any():
            df.loc[mask, 'llm_score'] = data['score']
            df.loc[mask, 'llm_reason'] = data.get('reason', '')

    # Process in batches
    batches = [
        to_process.iloc[i:i + LLM_BATCH_SIZE]
        for i in range(0, len(to_process), LLM_BATCH_SIZE)
    ]

    for batch_idx, batch in enumerate(batches):
        print(f"  [llm] Batch {batch_idx + 1}/{len(batches)} "
              f"({len(batch)} records)...")

        # Format accounts for prompt
        accounts_text = "\n".join(
            f"{i+1}. {_format_account_for_prompt(row)}"
            for i, (_, row) in enumerate(batch.iterrows())
        )

        # Call API
        try:
            results = _call_deepseek(accounts_text)
        except Exception as e:
            print(f"  [llm] Batch {batch_idx + 1} failed: {e}")
            print(f"  [llm] Skipping batch, records will keep rules_score")
            continue

        # Map results back to usernames
        result_map = {}
        for r in results:
            uname = r.get('username', '').lower().lstrip('@')
            result_map[uname] = r

        for _, row in batch.iterrows():
            username = row['username']
            if username in result_map:
                r = result_map[username]
                llm_score = float(r.get('score', 0.5))
                llm_reason = r.get('reason', '')
            else:
                # LLM didn't return this username — default to neutral
                llm_score = 0.5
                llm_reason = 'not returned by LLM'

            # Update DataFrame
            mask = df['username'] == username
            df.loc[mask, 'llm_score'] = llm_score
            df.loc[mask, 'llm_reason'] = llm_reason

            # Cache for resume
            scored[username] = {'score': llm_score, 'reason': llm_reason}

        # Save progress after each batch
        progress["scored_usernames"] = scored
        _save_progress(progress)

        # Small delay between batches to be respectful to API
        if batch_idx < len(batches) - 1:
            time.sleep(1)

    # --- Compute final scores ---
    # For "maybe" records: use LLM score (it's the expert opinion)
    # For "yes"/"no" records: keep rules score
    for idx, row in df.iterrows():
        if row['rules_classification'] == 'maybe' and row['llm_score'] is not None:
            df.at[idx, 'final_score'] = float(row['llm_score'])
            if float(row['llm_score']) >= FINAL_INCLUSION_THRESHOLD:
                df.at[idx, 'final_classification'] = 'yes'
            else:
                df.at[idx, 'final_classification'] = 'no'

    # Stats
    final_yes = (df['final_classification'] == 'yes').sum()
    print(f"\n[llm_curator] Final results:")
    print(f"  Total curated vendors: {final_yes}")
    print(f"  Rejected: {(df['final_classification'] == 'no').sum()}")

    return df


if __name__ == "__main__":
    import sys
    from .data_loader import load_data
    from .rules_engine import run_rules_engine

    if len(sys.argv) < 2:
        print("Usage: python -m curation.llm_curator <path_to_csv>")
        sys.exit(1)

    df = load_data(sys.argv[1])
    df = run_rules_engine(df)
    df = run_llm_curation(df)

    # Show curated vendors
    curated = df[df['final_classification'] == 'yes'].sort_values('final_score', ascending=False)
    print(f"\n--- Top curated vendors ({len(curated)}) ---")
    for _, row in curated.head(20).iterrows():
        print(f"  @{row['username']} — score: {row['final_score']:.2f} — {row['biography'][:60]}")
