"""
Merge scraper results into vendors.json and apply Instagram fallback for ALL vendors.
This script:
1. Loads the new scrape results
2. Updates vendors.json with new image data
3. Applies Instagram fallback to ANY vendor with empty/missing images (including Etsy)
4. Copies to website/ and root directories for GitHub Pages
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "scraper" / "output"
VENDORS_FILE = BASE_DIR / "website" / "vendors.json"
INSTAGRAM_IMAGES_FILE = BASE_DIR / "data" / "vendor_images.json"


def slugify(text):
    """Convert text to URL-friendly slug."""
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def find_instagram_images(username, instagram_images):
    """Find Instagram images for a username (try multiple variations)."""
    variations = [
        username,
        f"_{username}",
        username.replace('_', ''),
        username.replace('-', '_'),
        username.replace('.', ''),
        username.replace('_', '.')
    ]
    
    for variant in variations:
        images = instagram_images.get(variant)
        if images:
            return images[:3]  # Max 3 Instagram images
    
    return None


def main():
    print("="*70)
    print("🔄 MERGE SCRAPER RESULTS AND APPLY INSTAGRAM FALLBACK")
    print("="*70)
    
    # Load data
    print("\n📂 Loading data...")
    with open(VENDORS_FILE, 'r') as f:
        vendors_data = json.load(f)
    
    with open(INSTAGRAM_IMAGES_FILE, 'r') as f:
        instagram_images = json.load(f)
    
    # Load scrape results
    results_file = OUTPUT_DIR / "non_etsy_results_v2.json"
    if not results_file.exists():
        print(f"❌ Results file not found: {results_file}")
        return
    
    with open(results_file, 'r') as f:
        scrape_results = json.load(f)
    
    print(f"   ✓ {len(vendors_data['vendors'])} vendors")
    print(f"   ✓ {len(scrape_results)} scrape results")
    print(f"   ✓ {len(instagram_images)} Instagram profiles")
    
    # Create lookup for scrape results (skip entries without username)
    results_by_username = {}
    for r in scrape_results:
        if 'username' in r:
            results_by_username[r['username']] = r
        else:
            print(f"   ⚠️ Skipping result without username: {r.get('name', 'unknown')}")
    
    # Update vendors
    print("\n🔄 Updating vendor data...")
    updated_count = 0
    fallback_count = 0
    already_have_images = 0
    no_images_available = 0
    
    for vendor in vendors_data['vendors']:
        username = vendor['username']
        slug = slugify(username)
        
        # Check if vendor already has images
        existing_images = vendor.get('images', [])
        
        # Priority 1: Use new scrape results if available
        if username in results_by_username:
            result = results_by_username[username]
            vendor['images'] = result['images']
            updated_count += 1
            print(f"   ✓ {username}: {len(result['images'])} images from {result['source']}")
        
        # Priority 2: Keep existing images if they exist and are valid
        elif existing_images and len(existing_images) > 0:
            # Verify images exist on disk
            valid_images = []
            for img_path in existing_images:
                full_path = BASE_DIR / img_path
                if full_path.exists():
                    valid_images.append(img_path)
            
            if valid_images:
                vendor['images'] = valid_images
                already_have_images += 1
            else:
                # Existing images are broken, try Instagram fallback
                instagram_imgs = find_instagram_images(username, instagram_images)
                if instagram_imgs:
                    # Convert Instagram URLs to relative paths
                    # We'll use the URLs directly since they're already hosted
                    vendor['images'] = instagram_imgs
                    fallback_count += 1
                    print(f"   📸 {username}: {len(instagram_imgs)} Instagram images (fallback)")
                else:
                    vendor['images'] = []
                    no_images_available += 1
        
        # Priority 3: Apply Instagram fallback if no images at all
        else:
            instagram_imgs = find_instagram_images(username, instagram_images)
            if instagram_imgs:
                vendor['images'] = instagram_imgs
                fallback_count += 1
                print(f"   📸 {username}: {len(instagram_imgs)} Instagram images (fallback)")
            else:
                vendor['images'] = []
                no_images_available += 1
    
    # Update timestamp
    from datetime import datetime
    vendors_data['generated_at'] = datetime.now().isoformat()
    
    # Save updated vendors.json
    print(f"\n💾 Saving updated vendors.json...")
    with open(VENDORS_FILE, 'w') as f:
        json.dump(vendors_data, f, indent=2)
    print(f"   ✓ Saved to {VENDORS_FILE}")
    
    # Copy to root for GitHub Pages
    root_vendors_file = BASE_DIR / "vendors.json"
    with open(root_vendors_file, 'w') as f:
        json.dump(vendors_data, f, indent=2)
    print(f"   ✓ Copied to {root_vendors_file}")
    
    # Copy index.html if it changed
    website_index = BASE_DIR / "website" / "index.html"
    root_index = BASE_DIR / "index.html"
    if website_index.exists():
        import shutil
        shutil.copy(website_index, root_index)
        print(f"   ✓ Copied index.html to root")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"✅ UPDATE COMPLETE")
    print(f"{'='*70}")
    print(f"📊 Statistics:")
    print(f"   Total vendors:               {len(vendors_data['vendors'])}")
    print(f"   Updated from scrape:         {updated_count}")
    print(f"   Already had images:          {already_have_images}")
    print(f"   Instagram fallback applied:  {fallback_count}")
    print(f"   No images available:         {no_images_available}")
    print(f"\n✨ vendors.json updated and ready for commit!")


if __name__ == "__main__":
    main()
