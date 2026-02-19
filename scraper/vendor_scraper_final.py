"""
Vendor product scraping pipeline for festival vendors - Final Version.
Uses direct scraping for most platforms, Apify for Etsy.
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
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = BASE_DIR / "images"
OUTPUT_DIR = BASE_DIR / "scraper" / "output"
VENDORS_FILE = BASE_DIR / "website" / "vendors.json"

APIFY_TOKEN = os.environ.get('APIFY_TOKEN')
APIFY_API_BASE = "https://api.apify.com/v2"

# Ensure directories exist
IMAGES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
}


def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def download_and_resize_image(url, output_path, max_width=800):
    """Download an image and resize it to max_width, maintaining aspect ratio."""
    try:
        if url.startswith('//'):
            url = 'https:' + url
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        
        # Resize if wider than max_width
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        img.save(output_path, 'JPEG', quality=85)
        return True
    except Exception as e:
        print(f"  ⚠️  Failed: {str(e)[:60]}")
        return False


def scrape_shopify(vendor):
    """Scrape Shopify store using products.json endpoint."""
    print(f"\n🛍️  Scraping Shopify: {vendor['username']}")
    
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
        
        print(f"  ✅ Found {len(image_urls)} images")
        return {
            'images': image_urls,
            'description': description,
            'source': 'shopify_api'
        }
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def scrape_etsy_apify(vendor):
    """Scrape Etsy store using Apify actor (Etsy blocks direct scraping)."""
    print(f"\n🎨 Scraping Etsy (via Apify): {vendor['username']}")
    
    if not APIFY_TOKEN:
        print("  ❌ APIFY_TOKEN not set")
        return None
    
    shop_url = vendor['shop_url']
    
    # Use the verified Etsy scraper actor
    actor_id = "epctex/etsy-scraper"
    run_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs"
    
    headers = {
        'Authorization': f'Bearer {APIFY_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Simplified input - just scrape the shop page
    input_data = {
        "startUrls": [shop_url],
        "maxItems": 10,
        "endPage": 1,
        "proxy": {"useApifyProxy": True}
    }
    
    try:
        # Start the actor
        print(f"  ⏳ Starting Apify actor...")
        response = requests.post(run_url, json=input_data, headers=headers, params={'token': APIFY_TOKEN}, timeout=30)
        
        if response.status_code == 404:
            print(f"  ❌ Actor not found. Trying alternative...")
            # Try alternative actor
            actor_id = "jupri/etsy-scraper"
            run_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs"
            response = requests.post(run_url, json=input_data, headers=headers, params={'token': APIFY_TOKEN}, timeout=30)
        
        response.raise_for_status()
        run_info = response.json()
        run_id = run_info['data']['id']
        
        print(f"  ⏳ Waiting for results (run ID: {run_id[:8]}...)...")
        
        # Poll for completion (max 3 minutes)
        for attempt in range(36):
            time.sleep(5)
            status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
            status_response = requests.get(status_url, params={'token': APIFY_TOKEN})
            
            if status_response.status_code != 200:
                continue
                
            status_data = status_response.json()
            status = status_data['data']['status']
            
            if status == 'SUCCEEDED':
                # Get results
                dataset_id = status_data['data']['defaultDatasetId']
                results_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
                results_response = requests.get(results_url, params={'token': APIFY_TOKEN})
                results = results_response.json()
                
                if not results:
                    print(f"  ⚠️  No results returned")
                    return None
                
                # Extract images and description
                image_urls = []
                description = ""
                
                for item in results[:10]:
                    # Get shop/product description
                    if not description:
                        description = (item.get('shopDescription') or 
                                     item.get('description') or 
                                     item.get('title', ''))
                    
                    # Get product images
                    if item.get('images'):
                        imgs = item['images']
                        if isinstance(imgs, list):
                            for img in imgs:
                                if isinstance(img, str):
                                    image_urls.append(img)
                                elif isinstance(img, dict):
                                    image_urls.append(img.get('url', img.get('src', '')))
                                if len(image_urls) >= 5:
                                    break
                    
                    # Also check single image field
                    if item.get('image') and len(image_urls) < 5:
                        image_urls.append(item['image'])
                    
                    if len(image_urls) >= 5:
                        break
                
                print(f"  ✅ Found {len(image_urls)} images")
                return {
                    'images': image_urls[:5],
                    'description': description[:200],
                    'source': 'etsy_apify'
                }
                
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                print(f"  ❌ Actor run {status}")
                return None
            
            if attempt % 6 == 0:
                print(f"  ⏳ Still waiting... ({attempt * 5}s elapsed)")
        
        print("  ⚠️  Timeout (3min)")
        return None
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def scrape_bigcartel_direct(vendor):
    """Scrape BigCartel store directly from HTML."""
    print(f"\n🛒 Scraping BigCartel: {vendor['username']}")
    
    shop_url = vendor['shop_url']
    
    try:
        response = requests.get(shop_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        image_urls = []
        img_tags = soup.find_all('img', class_=re.compile(r'product|item'))
        if not img_tags:
            img_tags = soup.find_all('img')
        
        for img in img_tags:
            src = img.get('data-src') or img.get('src')
            if src and not any(skip in src.lower() for skip in ['logo', 'icon', 'avatar']):
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(shop_url, src)
                
                if src not in image_urls:
                    image_urls.append(src)
                if len(image_urls) >= 5:
                    break
        
        description = ""
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            description = meta_desc.get('content', '')
        
        print(f"  ✅ Found {len(image_urls)} images")
        return {
            'images': image_urls,
            'description': description,
            'source': 'bigcartel_direct'
        }
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def scrape_custom_direct(vendor):
    """Scrape custom website directly from HTML."""
    print(f"\n🌐 Scraping custom site: {vendor['username']}")
    
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
            
            if any(skip in src.lower() for skip in ['logo', 'icon', 'favicon', 'avatar', 'profile']):
                continue
            
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = urljoin(shop_url, src)
            elif not src.startswith('http'):
                src = urljoin(shop_url, src)
            
            if 'product' in src.lower() or 'item' in src.lower() or 'gallery' in src.lower():
                if src not in image_urls:
                    image_urls.append(src)
            elif len(image_urls) < 10:
                if src not in image_urls:
                    image_urls.append(src)
            
            if len(image_urls) >= 10:
                break
        
        description = ""
        meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content', '')
        
        if not description:
            about_section = soup.find(class_=re.compile(r'about|description', re.I))
            if about_section:
                description = about_section.get_text()[:200].strip()
        
        print(f"  ✅ Found {len(image_urls)} images")
        return {
            'images': image_urls[:5],
            'description': description,
            'source': 'custom_direct'
        }
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def process_vendor(vendor):
    """Process a single vendor - scrape and save images."""
    username = vendor['username']
    shop_url = vendor['shop_url'].lower()
    vendor_slug = slugify(username)
    
    print(f"\n{'='*60}")
    print(f"Processing: {username}")
    print(f"URL: {shop_url}")
    
    # Determine platform and scrape
    scrape_result = None
    platform = "unknown"
    
    if 'shopify' in shop_url or 'myshopify' in shop_url:
        platform = "shopify"
        scrape_result = scrape_shopify(vendor)
    elif 'etsy.com' in shop_url:
        platform = "etsy"
        scrape_result = scrape_etsy_apify(vendor)
    elif 'bigcartel' in shop_url:
        platform = "bigcartel"
        scrape_result = scrape_bigcartel_direct(vendor)
    elif 'depop.com' in shop_url:
        platform = "depop"
        print("  ⏭️  Skipping Depop (manual)")
        return None
    else:
        platform = "custom"
        scrape_result = scrape_custom_direct(vendor)
    
    if not scrape_result or not scrape_result['images']:
        print("  ❌ No images found")
        return None
    
    # Create vendor image directory
    vendor_images_dir = IMAGES_DIR / vendor_slug
    vendor_images_dir.mkdir(exist_ok=True)
    
    # Download and resize images
    saved_images = []
    for i, img_url in enumerate(scrape_result['images'][:5]):
        output_path = vendor_images_dir / f"product_{i+1}.jpg"
        print(f"  📥 Downloading image {i+1}/5...", end=' ')
        if download_and_resize_image(img_url, output_path):
            saved_images.append(str(output_path.relative_to(BASE_DIR)))
            print("✅")
        else:
            print("❌")
    
    if not saved_images:
        print("  ❌ No images successfully downloaded")
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
    
    print(f"  💾 Saved metadata: {metadata_path.name}")
    print(f"  📸 Total: {len(saved_images)}/5 images")
    
    return metadata


def main():
    """Main entry point."""
    print("🚀 Vendor Product Scraper - Phase 1 Test Run (Final)")
    print("="*60)
    
    # Load vendors
    with open(VENDORS_FILE, 'r') as f:
        vendors_data = json.load(f)
    
    vendors = vendors_data['vendors']
    
    # Categorize vendors by platform
    platforms = {
        'shopify': [],
        'etsy': [],
        'bigcartel': [],
        'depop': [],
        'custom': []
    }
    
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
        print(f"  {platform}: {len(vlist)}")
    
    # Test run: one vendor per platform
    print(f"\n🧪 TEST RUN: Processing 1 vendor per platform\n")
    
    test_vendors = []
    results = []
    
    # Pick one from each platform (skip depop)
    for platform in ['shopify', 'etsy', 'bigcartel', 'custom']:
        if platforms[platform]:
            test_vendors.append(platforms[platform][0])
    
    for vendor in test_vendors:
        try:
            result = process_vendor(vendor)
            if result:
                results.append(result)
        except Exception as e:
            print(f"  ❌ Fatal error processing {vendor['username']}: {e}")
            import traceback
            traceback.print_exc()
    
    # Save summary
    summary = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_processed': len(results),
        'total_attempted': len(test_vendors),
        'success_rate': f"{len(results)}/{len(test_vendors)}",
        'results': results
    }
    
    summary_path = OUTPUT_DIR / f"test_run_final_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ Test run complete!")
    print(f"   Success: {len(results)}/{len(test_vendors)} vendors")
    print(f"   Summary: {summary_path}")
    print(f"   Images: {IMAGES_DIR}")
    print(f"   Metadata: {OUTPUT_DIR}")
    
    # Show results
    print(f"\n📋 Results Summary:")
    for r in results:
        print(f"  ✅ {r['username']} ({r['platform']}): {len(r['images'])} images - {r['source']}")


if __name__ == "__main__":
    main()
