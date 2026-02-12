"""
Category Tagger: Assigns 1-2 browseable categories to each curated vendor.
Uses DeepSeek to analyze bio + website description and map to fixed taxonomy.
Only runs on curated vendors (~200-400), so cost is minimal.
"""
import json
import time
import requests
import pandas as pd
from .config import (
    DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL,
    LLM_MAX_RETRIES, LLM_RETRY_DELAY, LLM_TIMEOUT,
    CATEGORIES,
)

SYSTEM_PROMPT = f"""You are a product categorizer for a festival vendor directory.

Given vendor information, assign 1-2 categories from this EXACT list:
{json.dumps(CATEGORIES)}

Rules:
- Use ONLY categories from the list above (exact spelling)
- Assign 1 category minimum, 2 maximum
- If truly unclear, use "Other Handmade"
- Respond ONLY with valid JSON, no markdown or extra text"""

USER_PROMPT_TEMPLATE = """Categorize these vendors. Return a JSON array with objects:
- "username": the account username
- "categories": array of 1-2 category strings from the allowed list

Vendors:
{vendors_text}

JSON response:"""


def _format_vendor_for_prompt(row: pd.Series) -> str:
    """Format vendor data for categorization prompt."""
    parts = [f"@{row['username']}"]

    bio = row.get('biography', '').strip()
    if bio:
        parts.append(f"Bio: \"{bio[:200]}\"")

    url = row.get('external_url', '').strip()
    if url:
        parts.append(f"URL: {url}")

    desc = row.get('website_description', '').strip()
    if desc and desc != '|':
        parts.append(f"Site: \"{desc[:150]}\"")

    return ' | '.join(parts)


def _call_deepseek_categorize(vendors_text: str) -> list[dict]:
    """Call DeepSeek for categorization."""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                vendors_text=vendors_text
            )},
        ],
        "temperature": 0.1,
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

            # Strip markdown fences
            if content.startswith('```'):
                content = content.split('\n', 1)[1] if '\n' in content else content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

            results = json.loads(content)
            return results if isinstance(results, list) else [results]

        except Exception as e:
            print(f"  [categorizer] Error (attempt {attempt+1}): {e}")
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(LLM_RETRY_DELAY * (2 ** attempt))
            else:
                return []


def run_category_tagger(df: pd.DataFrame, batch_size: int = 15) -> pd.DataFrame:
    """
    Assign categories to curated vendors.
    Only processes rows where final_classification == 'yes'.
    """
    df = df.copy()
    df['categories'] = ''

    curated_mask = df['final_classification'] == 'yes'
    curated = df[curated_mask]

    if len(curated) == 0:
        print("[category_tagger] No curated vendors to categorize")
        return df

    print(f"[category_tagger] Categorizing {len(curated)} vendors...")

    batches = [
        curated.iloc[i:i + batch_size]
        for i in range(0, len(curated), batch_size)
    ]

    for batch_idx, batch in enumerate(batches):
        print(f"  [categorizer] Batch {batch_idx + 1}/{len(batches)}...")

        vendors_text = "\n".join(
            f"{i+1}. {_format_vendor_for_prompt(row)}"
            for i, (_, row) in enumerate(batch.iterrows())
        )

        results = _call_deepseek_categorize(vendors_text)

        # Map results back
        result_map = {}
        for r in results:
            uname = r.get('username', '').lower().lstrip('@')
            cats = r.get('categories', ['Other Handmade'])
            # Validate categories against allowed list
            valid_cats = [c for c in cats if c in CATEGORIES]
            if not valid_cats:
                valid_cats = ['Other Handmade']
            result_map[uname] = valid_cats

        for _, row in batch.iterrows():
            username = row['username']
            cats = result_map.get(username, ['Other Handmade'])
            df.loc[df['username'] == username, 'categories'] = json.dumps(cats)

        if batch_idx < len(batches) - 1:
            time.sleep(1)

    # Stats
    print(f"\n[category_tagger] Category distribution:")
    all_cats = []
    for cats_json in df.loc[curated_mask, 'categories']:
        if cats_json:
            try:
                all_cats.extend(json.loads(cats_json))
            except json.JSONDecodeError:
                pass
    for cat in CATEGORIES:
        count = all_cats.count(cat)
        if count > 0:
            print(f"  {cat}: {count}")

    return df


if __name__ == "__main__":
    print("Run via: python -m curation.run_pipeline")
    print("Category tagger runs as part of the full pipeline.")
