"""
Category Tagger v2: Assigns categories using bio + website metadata.
Only runs on final YES vendors. Uses DeepSeek with improved prompt.
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

SYSTEM_PROMPT = f"""You categorize festival vendors. Assign 1-2 categories from this EXACT list:
{json.dumps(CATEGORIES)}

Base your decision on what they SELL, not just vibes.
- Clothing/wearables → "Festival Clothing"
- Jewelry, necklaces, bracelets, kandi, chains → "Jewelry & Accessories"
- Paintings, prints, digital art, murals → "Art & Prints"
- Lamps, furniture, tapestries → "Home Decor"
- Figurines, plushies, sculptures, toys → "Toys & Sculptures"
- Bags, fanny packs, hydration packs → "Bags & Packs"
- Face gems, body paint, cosmetics → "Body Art & Cosmetics"
- Stickers, patches, pins, enamel pins → "Stickers & Patches"
- If unclear, use "Other Handmade"

Also generate 3-5 short search tags (2-3 words each) that describe what they sell.
Example tags: "beaded jewelry", "tie dye shirts", "resin earrings", "crochet tops"

Respond ONLY with JSON array. No markdown."""

USER_PROMPT_TEMPLATE = """Categorize and tag these vendors:

{vendors_text}

Return JSON: [{{"username": "x", "categories": ["Cat1"], "tags": ["tag1", "tag2", "tag3"]}}]"""


def _format_vendor(row: pd.Series) -> str:
    parts = [f"@{row['username']}"]
    bio = str(row.get('biography', '')).strip()
    if bio and bio != 'nan':
        parts.append(f'Bio: "{bio[:250]}"')
    url = str(row.get('external_url', '')).strip()
    if url and url != 'nan':
        parts.append(f"URL: {row.get('domain', url[:50])}")
    desc = str(row.get('website_description', '')).strip()
    if desc and desc not in ('', '|', 'nan'):
        parts.append(f'Site: "{desc[:150]}"')
    title = str(row.get('website_title', '')).strip()
    if title and title != 'nan':
        parts.append(f'Title: "{title[:80]}"')
    return ' | '.join(parts)


def _call_deepseek(vendors_text: str) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(vendors_text=vendors_text)},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    for attempt in range(LLM_MAX_RETRIES):
        try:
            resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=LLM_TIMEOUT)
            resp.raise_for_status()
            content = resp.json()['choices'][0]['message']['content'].strip()
            if content.startswith('```'):
                content = content.split('\n', 1)[1] if '\n' in content else content[3:]
            if content.endswith('```'):
                content = content[:-3]
            results = json.loads(content.strip())
            return results if isinstance(results, list) else [results]
        except Exception as e:
            print(f"  [categorizer] Error (attempt {attempt+1}): {e}")
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(LLM_RETRY_DELAY * (2 ** attempt))
    return []


def run_category_tagger(df: pd.DataFrame, batch_size: int = 10) -> pd.DataFrame:
    df = df.copy()
    df['categories'] = ''
    df['vendor_tags'] = ''

    curated = df[df['final_classification'] == 'yes']
    if len(curated) == 0:
        print("[category_tagger v2] No vendors to categorize")
        return df

    print(f"[category_tagger v2] Categorizing {len(curated)} vendors...")

    batches = [curated.iloc[i:i+batch_size] for i in range(0, len(curated), batch_size)]

    for bi, batch in enumerate(batches):
        print(f"  Batch {bi+1}/{len(batches)}...")
        text = "\n".join(f"{i+1}. {_format_vendor(row)}" for i, (_, row) in enumerate(batch.iterrows()))
        results = _call_deepseek(text)

        rmap = {}
        for r in results:
            u = r.get('username', '').lower().lstrip('@')
            cats = [c for c in r.get('categories', []) if c in CATEGORIES] or ['Other Handmade']
            tags = r.get('tags', [])[:5]
            rmap[u] = {'categories': cats, 'tags': tags}

        for _, row in batch.iterrows():
            u = row['username']
            data = rmap.get(u, {'categories': ['Other Handmade'], 'tags': []})
            df.loc[df['username'] == u, 'categories'] = json.dumps(data['categories'])
            df.loc[df['username'] == u, 'vendor_tags'] = json.dumps(data['tags'])

        if bi < len(batches) - 1:
            time.sleep(1)

    # Stats
    print(f"\n[category_tagger v2] Distribution:")
    all_cats = []
    for c in df.loc[df['final_classification'] == 'yes', 'categories'].dropna():
        try: all_cats.extend(json.loads(c))
        except: pass
    from collections import Counter
    for cat, count in Counter(all_cats).most_common():
        print(f"  {cat}: {count}")

    return df


if __name__ == "__main__":
    print("Run via pipeline orchestrator")
