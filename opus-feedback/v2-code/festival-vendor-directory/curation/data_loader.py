"""
Data loader: CSV ingestion + normalization.
Handles the messy Instagram scraper output and produces a clean DataFrame.
"""
import pandas as pd
import re
from urllib.parse import unquote


def extract_clean_url(raw_url: str) -> str:
    """Extract actual URL from Instagram's redirect wrapper."""
    if not raw_url or pd.isna(raw_url):
        return ""
    raw_url = str(raw_url).strip()

    # Instagram wraps external URLs: https://l.instagram.com/?u=ENCODED_URL&e=...
    match = re.search(r'[?&]u=([^&]+)', raw_url)
    if match:
        return unquote(match.group(1))

    # Already a clean URL
    if raw_url.startswith("http"):
        return raw_url

    return ""


def extract_domain(url: str) -> str:
    """Extract domain from URL for matching against known brands."""
    if not url:
        return ""
    # Remove protocol and www
    domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0].lower()
    return domain


def load_data(csv_path: str) -> pd.DataFrame:
    """
    Load scraped Instagram CSV and normalize into clean columns.

    Expected input columns (from the scraper):
        username, biography, profileURL, externalURL,
        websiteOgDescription, websiteMetaDescription,
        tags, followersCount, isBusinessAccount

    Additional columns that may exist:
        id, postsCount, followsCount, isPrivate,
        websiteTitle, websiteOgTitle, websiteName, etc.

    Returns DataFrame with standardized columns.
    """
    # Read CSV — be generous with parsing since scraper output can be messy
    df = pd.read_csv(csv_path, dtype=str, on_bad_lines='skip', encoding='utf-8')

    # Standardize column names (strip whitespace, lowercase)
    df.columns = df.columns.str.strip().str.lower()

    # --- Normalize key columns ---

    # Username: strip whitespace, lowercase
    if 'username' in df.columns:
        df['username'] = df['username'].str.strip().str.lower()
    else:
        raise ValueError("CSV must have a 'username' column")

    # Biography: fill NaN with empty string, strip
    df['biography'] = df.get('biography', pd.Series(dtype=str)).fillna('').str.strip()

    # Follower count: convert to int, default 0
    for col in ['followerscount', 'followers_count', 'followers']:
        if col in df.columns:
            df['followers'] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            break
    else:
        df['followers'] = 0

    # Following count: convert to int, default 0
    for col in ['followscount', 'follows_count', 'following', 'followingcount']:
        if col in df.columns:
            df['following'] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            break
    else:
        df['following'] = 0

    # Posts count
    for col in ['postscount', 'posts_count', 'posts']:
        if col in df.columns:
            df['posts'] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            break
    else:
        df['posts'] = 0

    # Business account flag
    for col in ['isbusinessaccount', 'is_business_account', 'is_business']:
        if col in df.columns:
            df['is_business'] = df[col].astype(str).str.upper().isin(['TRUE', '1', 'YES'])
            break
    else:
        df['is_business'] = False

    # Private account flag
    for col in ['isprivate', 'is_private']:
        if col in df.columns:
            df['is_private'] = df[col].astype(str).str.upper().isin(['TRUE', '1', 'YES'])
            break
    else:
        df['is_private'] = False

    # External URL: clean Instagram redirect wrapper
    raw_url_col = None
    for col in ['externalurl', 'external_url', 'website']:
        if col in df.columns:
            raw_url_col = col
            break

    df['external_url'] = (
        df[raw_url_col].apply(extract_clean_url) if raw_url_col
        else ''
    )
    df['domain'] = df['external_url'].apply(extract_domain)

    # Profile URL
    if 'profileurl' in df.columns:
        df['profile_url'] = df['profileurl'].fillna('')
    elif 'profile_url' not in df.columns:
        df['profile_url'] = 'https://www.instagram.com/' + df['username'] + '/'

    # Website descriptions: combine available text signals
    desc_cols = ['websiteogdescription', 'websitemetadescription',
                 'website_og_description', 'website_meta_description']
    desc_parts = []
    for col in desc_cols:
        if col in df.columns:
            desc_parts.append(df[col].fillna(''))

    if desc_parts:
        df['website_description'] = (
            pd.concat(desc_parts, axis=1)
            .apply(lambda row: ' | '.join(filter(None, row.unique())), axis=1)
        )
    else:
        df['website_description'] = ''

    # Website title
    for col in ['websitetitle', 'website_title', 'websiteogtitle']:
        if col in df.columns:
            df['website_title'] = df[col].fillna('')
            break
    else:
        df['website_title'] = ''

    # Tags
    df['tags'] = df.get('tags', pd.Series(dtype=str)).fillna('')

    # --- Combine all text for analysis ---
    df['all_text'] = (
        df['biography'] + ' | ' +
        df['website_description'] + ' | ' +
        df['website_title'] + ' | ' +
        df['tags']
    ).str.lower()

    # --- Dedup by username ---
    df = df.drop_duplicates(subset='username', keep='first')

    # --- Drop private accounts (can't see their content) ---
    df = df[~df['is_private']].copy()

    # Select and order final columns
    output_cols = [
        'username', 'biography', 'followers', 'following', 'posts',
        'is_business', 'external_url', 'domain', 'profile_url',
        'website_description', 'website_title', 'tags', 'all_text'
    ]
    # Only include columns that exist
    output_cols = [c for c in output_cols if c in df.columns]

    print(f"[data_loader] Loaded {len(df)} records from {csv_path}")
    print(f"[data_loader] Columns: {output_cols}")

    return df[output_cols].reset_index(drop=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m curation.data_loader <path_to_csv>")
        sys.exit(1)
    df = load_data(sys.argv[1])
    print(f"\nSample (first 5 rows):")
    print(df[['username', 'followers', 'is_business', 'domain']].head())
    print(f"\nBusiness accounts: {df['is_business'].sum()}")
    print(f"Have external URL: {(df['external_url'] != '').sum()}")
    print(f"Follower range: {df['followers'].min()} - {df['followers'].max()}")
