"""
Build Site Data: Transforms curated_vendors.json into the optimized
vendors.json format that the static website consumes.

Handles:
  - Cleaning/truncating bios for display
  - Generating search-friendly text
  - Building category index
  - Constructing Instagram profile pic URLs
"""
import json
import re
import sys
import os


def clean_bio(bio: str, max_length: int = 120) -> str:
    """Clean biography for display on vendor card."""
    if not bio:
        return ""
    # Remove emoji (optional — keep for now, they're fun)
    # Remove excessive whitespace
    bio = re.sub(r'\s+', ' ', bio).strip()
    # Truncate
    if len(bio) > max_length:
        bio = bio[:max_length].rsplit(' ', 1)[0] + '…'
    return bio


def instagram_pic_url(username: str) -> str:
    """
    Construct Instagram profile picture URL.
    Note: Direct IG profile pic URLs are unreliable/blocked.
    We'll use a placeholder and let the website handle it.
    The website can use the Instagram embed or a generic avatar.
    """
    return f"https://www.instagram.com/{username}/"


def get_shop_url(vendor: dict) -> str:
    """Determine the best URL to link to for shopping."""
    ext_url = vendor.get('external_url', '')
    if ext_url:
        # If it's a linktree or similar, still use it
        return ext_url
    # Fallback to Instagram profile
    return vendor.get('profile_url', f"https://www.instagram.com/{vendor['username']}/")


def build_site_data(input_path: str, output_path: str):
    """
    Transform curated_vendors.json → vendors.json for the website.
    """
    with open(input_path, 'r') as f:
        vendors = json.load(f)

    site_vendors = []
    all_categories = set()

    for v in vendors:
        categories = v.get('categories', ['Other Handmade'])
        if isinstance(categories, str):
            try:
                categories = json.loads(categories)
            except json.JSONDecodeError:
                categories = ['Other Handmade']

        for cat in categories:
            all_categories.add(cat)

        shop_url = get_shop_url(v)

        site_vendor = {
            'id': v['username'],
            'name': v.get('website_title', '') or f"@{v['username']}",
            'username': v['username'],
            'bio': clean_bio(v.get('biography', '')),
            'categories': categories,
            'shop_url': shop_url,
            'instagram_url': v.get('profile_url', f"https://www.instagram.com/{v['username']}/"),
            'domain': v.get('domain', ''),
            'followers': v.get('followers', 0),
            'score': v.get('confidence_score', 0),
            # Search text: combine all useful text for client-side search
            'search_text': ' '.join(filter(None, [
                v['username'],
                v.get('biography', ''),
                v.get('website_title', ''),
                v.get('website_description', ''),
                ' '.join(categories),
            ])).lower(),
        }

        site_vendors.append(site_vendor)

    # Sort by confidence score (highest first)
    site_vendors.sort(key=lambda x: x['score'], reverse=True)

    # Build output
    site_data = {
        'generated_at': __import__('datetime').datetime.now().isoformat(),
        'total_vendors': len(site_vendors),
        'categories': sorted(all_categories),
        'vendors': site_vendors,
    }

    # Write output
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(site_data, f, indent=2)

    print(f"[build_site_data] Generated {output_path}")
    print(f"  Vendors: {len(site_vendors)}")
    print(f"  Categories: {sorted(all_categories)}")

    return site_data


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "output/curated_vendors.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "website/vendors.json"
    build_site_data(input_path, output_path)
