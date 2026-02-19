"""
Test the v2 scraper on a small sample of vendors.
"""
import sys
sys.path.insert(0, '/home/bumby/.openclaw/workspace/festival-vendors/scraper')

from vendor_scraper_v2 import *

def main():
    print("="*60)
    print("🧪 TEST RUN - Enhanced Scraper V2")
    print("="*60)
    
    # Load data
    with open(VENDORS_FILE, 'r') as f:
        vendors_data = json.load(f)
    vendors = vendors_data['vendors']
    
    with open(INSTAGRAM_IMAGES_FILE, 'r') as f:
        instagram_images = json.load(f)
    
    # Pick test vendors (one of each platform)
    test_vendors = []
    
    # Find one Shopify
    for v in vendors:
        if 'shopify' in v.get('shop_url', '').lower():
            test_vendors.append(v)
            break
    
    # Find one BigCartel
    for v in vendors:
        if 'bigcartel' in v.get('shop_url', '').lower():
            test_vendors.append(v)
            break
    
    # Find one custom
    for v in vendors:
        url = v.get('shop_url', '').lower()
        if url and 'shopify' not in url and 'bigcartel' not in url and 'etsy' not in url and 'depop' not in url:
            test_vendors.append(v)
            break
    
    print(f"\n🎯 Testing {len(test_vendors)} vendors")
    
    results = []
    for vendor in test_vendors:
        try:
            result = process_vendor(vendor, instagram_images)
            if result:
                results.append(result)
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"✅ Test complete: {len(results)}/{len(test_vendors)} successful")
    print(f"{'='*60}")
    
    for r in results:
        print(f"  ✓ {r['username']} ({r['platform']}) - {len(r['images'])} images - {r['source']}")

if __name__ == "__main__":
    main()
