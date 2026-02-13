"""
Build Site Data v2: Transforms curated_vendors.json → vendors.json for website.
Now includes vendor_tags for better search/filtering.
"""
import json, re, sys, os


def clean_bio(bio, max_length=120):
    if not bio: return ""
    bio = re.sub(r'\s+', ' ', bio).strip()
    if len(bio) > max_length:
        bio = bio[:max_length].rsplit(' ', 1)[0] + '…'
    return bio


def get_shop_url(v):
    ext = v.get('external_url', '')
    if ext: return ext
    return v.get('profile_url', f"https://www.instagram.com/{v['username']}/")


def build_site_data(input_path, output_path):
    with open(input_path, 'r') as f:
        vendors = json.load(f)

    site_vendors = []
    all_categories = set()
    all_tags = set()

    for v in vendors:
        cats = v.get('categories', ['Other Handmade'])
        if isinstance(cats, str):
            try: cats = json.loads(cats)
            except: cats = ['Other Handmade']

        tags = v.get('tags', [])
        if isinstance(tags, str):
            try: tags = json.loads(tags)
            except: tags = []

        for c in cats: all_categories.add(c)
        for t in tags: all_tags.add(t)

        shop_url = get_shop_url(v)

        site_vendors.append({
            'id': v['username'],
            'name': v.get('website_title', '') or f"@{v['username']}",
            'username': v['username'],
            'bio': clean_bio(v.get('biography', '')),
            'categories': cats,
            'tags': tags,
            'shop_url': shop_url,
            'instagram_url': v.get('profile_url', f"https://www.instagram.com/{v['username']}/"),
            'domain': v.get('domain', ''),
            'followers': v.get('followers', 0),
            'score': v.get('confidence_score', 0),
            'search_text': ' '.join(filter(None, [
                v['username'],
                v.get('biography', ''),
                v.get('website_title', ''),
                v.get('website_description', ''),
                ' '.join(cats),
                ' '.join(tags),
            ])).lower(),
        })

    site_vendors.sort(key=lambda x: x['score'], reverse=True)

    site_data = {
        'generated_at': __import__('datetime').datetime.now().isoformat(),
        'total_vendors': len(site_vendors),
        'categories': sorted(all_categories),
        'tags': sorted(all_tags),
        'vendors': site_vendors,
    }

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(site_data, f, indent=2)

    print(f"[build_site_data] {len(site_vendors)} vendors → {output_path}")
    print(f"  Categories: {sorted(all_categories)}")
    print(f"  Unique tags: {len(all_tags)}")


if __name__ == "__main__":
    inp = sys.argv[1] if len(sys.argv) > 1 else "output/curated_vendors.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "website/vendors.json"
    build_site_data(inp, out)
