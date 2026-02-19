"""
Comprehensive vendor product scraping pipeline.
- Shopify: Direct API (products.json)
- Etsy: Use Instagram images (already scraped)
- BigCartel: Direct HTML scraping
- Custom: Direct HTML scraping
- Depop: Skip (manual)
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests
from PIL import Image
from io import BytesIO
from bs4 import BeautifulSoup

# Configuration
BASE_DIR = Path(__file__).parent.parent
IMAGES_DIR = BASE_DIR / "images"
OUTPUT_DIR = BASE_DIR / "scraper" / "output"
VENDORS_FILE = BASE_DIR / "website" / "vendors.json"
INSTAGRAM_IMAGES_FILE = BASE_DIR / "data" / "vendor_images.json"

# Ensure directories exist
IMAGES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def download_and_resize_image(url, output_path, max_width=800):
    """Download an image and resize it."""
    try:
        if url.startswith('//'):
            url = 'https:' + url
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        
        # Resize if needed
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        img.save(output_path, 'JPEG', quality=85)
        return True
    except Exception as e:
        return False


def scrape_shopify(vendor):
    """Scrape Shopify via products.json API."""
    shop_url = vendor['shop_url']
    domain = urlparse(shop_url).netloc
    products_url = f"https://{domain}/products.json"
    
    try:
        response = requests.get(products_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        products = data.get('products', [])
        if not products:
            return None
        
        image_urls = []
        for product in products[:10]:
            if product.get('images'):
                for img in product['images']:
                    if img.get('src') and len(image_urls) < 5:
                        image_urls.append(img['src'])
            if len(image_urls) >= 5:
                break
        
        description = products[0].get('vendor', '') if products else ''
        
        return {
            'images': image_urls,
            'description': description,
            'source': 'shopify_api'
        }
    except Exception:
        return None


def scrape_etsy_instagram(vendor, instagram_images):
    """Use Instagram images for Etsy (faster and more reliable)."""
    username = vendor['username']
    
    # Try with and without underscore prefix
    images = instagram_images.get(username) or instagram_images.get(f"_{username}")
    
    if not images:
        return None
    
    # Get vendor bio as description
    description = vendor.get('bio', '')
    
    return {
        'images': images[:5],
        'description': description,
        'source': 'instagram_fallback'
    }


def scrape_generic_html(vendor):
    """Generic HTML scraper for BigCartel and custom sites."""
    shop_url = vendor['shop_url']
    
    try:
        response = requests.get(shop_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        image_urls = []
        img_tags = soup.find_all('img')
        
        for img in img_tags:
            src = img.get('data-src') or img.get('src')
            if not src:
                continue
            
            # Skip common non-product images
            if any(skip in src.lower() for skip in ['logo', 'icon', 'favicon', 'avatar', 'profile']):
                continue
            
            # Handle relative URLs
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = urljoin(shop_url, src)
            elif not src.startswith('http'):
                src = urljoin(shop_url, src)
            
            # Prefer product images
            if 'product' in src.lower() or 'item' in src.lower():
                image_urls.insert(0, src)
            elif src not in image_urls:
                image_urls.append(src)
            
            if len(image_urls) >= 10:
                break
        
        # Get description
        description = ""
        meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content', '')
        
        return {
            'images': image_urls[:5],
            'description': description,
            'source': 'html_scrape'
        }
    except Exception:
        return None


def process_vendor(vendor, instagram_images):
    """Process a single vendor."""
    username = vendor['username']
    shop_url = vendor['shop_url'].lower()
    vendor_slug = slugify(username)
    
    print(f"\n{'='*60}")
    print(f"📦 {username}")
    print(f"🔗 {shop_url[:60]}...")
    
    # Determine platform and scrape
    scrape_result = None
    platform = "unknown"
    
    if 'shopify' in shop_url or 'myshopify' in shop_url:
        platform = "shopify"
        print("🛍️  Shopify → products.json")
        scrape_result = scrape_shopify(vendor)
    elif 'etsy.com' in shop_url:
        platform = "etsy"
        print("🎨 Etsy → Instagram images")
        scrape_result = scrape_etsy_instagram(vendor, instagram_images)
    elif 'bigcartel' in shop_url:
        platform = "bigcartel"
        print("🛒 BigCartel → HTML scrape")
        scrape_result = scrape_generic_html(vendor)
    elif 'depop.com' in shop_url:
        platform = "depop"
        print("⏭️  Depop → SKIP (manual)")
        return None
    else:
        platform = "custom"
        print("🌐 Custom → HTML scrape")
        scrape_result = scrape_generic_html(vendor)
    
    if not scrape_result or not scrape_result['images']:
        print("❌ No images found")
        return None
    
    # Create vendor image directory
    vendor_images_dir = IMAGES_DIR / vendor_slug
    vendor_images_dir.mkdir(exist_ok=True)
    
    # Download and resize images
    saved_images = []
    print(f"📥 Downloading images: ", end='')
    for i, img_url in enumerate(scrape_result['images'][:5]):
        output_path = vendor_images_dir / f"product_{i+1}.jpg"
        if download_and_resize_image(img_url, output_path):
            saved_images.append(str(output_path.relative_to(BASE_DIR)))
            print("✓", end='')
        else:
            print("✗", end='')
    print(f" ({len(saved_images)}/5)")
    
    if not saved_images:
        print("❌ Download failed")
        return None
    
    # Create metadata JSON
    metadata = {
        'name': vendor.get('name', username),
        'username': username,
        'platform': platform,
        'images': saved_images,
        'description': scrape_result.get('description', ''),
        'shopUrl': vendor['shop_url'],
        'source': scrape_result.get('source', 'unknown')
    }
    
    metadata_path = OUTPUT_DIR / f"{vendor_slug}.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Success: {len(saved_images)} images saved")
    return metadata


def main():
    """Main entry point."""
    print("="*60)
    print("🚀 VENDOR PRODUCT SCRAPER - PHASE 1 TEST RUN")
    print("="*60)
    
    # Load data
    with open(VENDORS_FILE, 'r') as f:
        vendors_data = json.load(f)
    vendors = vendors_data['vendors']
    
    with open(INSTAGRAM_IMAGES_FILE, 'r') as f:
        instagram_images = json.load(f)
    
    # Categorize by platform
    platforms = {'shopify': [], 'etsy': [], 'bigcartel': [], 'depop': [], 'custom': []}
    
    for v in vendors:
        url = v.get('shop_url', '').lower()
        if 'shopify' in url or 'myshopify' in url:
            platforms['shopify'].append(v)
        elif 'etsy.com' in url:
            platforms['etsy'].append(v)
        elif 'bigcartel' in url:
            platforms['bigcartel'].append(v)
        elif 'depop.com' in url:
            platforms['depop'].append(v)
        elif url:
            platforms['custom'].append(v)
    
    print(f"\n📊 Platform Distribution:")
    for platform, vlist in platforms.items():
        print(f"   {platform.ljust(12)} {len(vlist):3d} vendors")
    
    print(f"\n🧪 TEST MODE: 1 vendor per platform")
    
    # Test: one vendor per platform
    test_vendors = []
    for platform in ['shopify', 'etsy', 'bigcartel', 'custom']:
        if platforms[platform]:
            test_vendors.append(platforms[platform][0])
    
    results = []
    for vendor in test_vendors:
        try:
            result = process_vendor(vendor, instagram_images)
            if result:
                results.append(result)
        except Exception as e:
            print(f"❌ Fatal error: {e}")
    
    # Save summary
    summary = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'mode': 'test_run',
        'attempted': len(test_vendors),
        'successful': len(results),
        'results': results
    }
    
    summary_path = OUTPUT_DIR / "PHASE1_TEST_SUMMARY.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ TEST RUN COMPLETE")
    print(f"{'='*60}")
    print(f"📊 Results: {len(results)}/{len(test_vendors)} successful")
    print(f"💾 Summary: {summary_path.name}")
    print(f"📁 Images: {IMAGES_DIR}")
    print(f"📁 Metadata: {OUTPUT_DIR}")
    
    print(f"\n📋 Platform Results:")
    for r in results:
        print(f"   ✅ {r['platform'].ljust(10)} {r['username'].ljust(20)} {len(r['images'])} images ({r['source']})")
    
    if len(results) < len(test_vendors):
        print(f"\n⚠️  {len(test_vendors) - len(results)} vendors failed - see logs above")


if __name__ == "__main__":
    main()
