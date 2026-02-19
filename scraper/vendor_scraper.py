"""
Vendor product scraping pipeline for festival vendors.
Handles Shopify, Etsy, BigCartel, and custom websites.
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from io import BytesIO

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


def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def download_and_resize_image(url, output_path, max_width=800):
    """
    Download an image and resize it to max_width, maintaining aspect ratio.
    Returns True if successful, False otherwise.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # Resize if wider than max_width
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        img.save(output_path, 'JPEG', quality=85)
        return True
    except Exception as e:
        print(f"  ❌ Failed to download {url}: {e}")
        return False


def scrape_shopify(vendor):
    """Scrape Shopify store using products.json endpoint."""
    print(f"\n🛍️  Scraping Shopify: {vendor['username']}")
    
    shop_url = vendor['shop_url']
    domain = urlparse(shop_url).netloc
    
    # Try to get products.json
    products_url = f"https://{domain}/products.json"
    
    try:
        response = requests.get(products_url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        products = data.get('products', [])
        if not products:
            print("  ⚠️  No products found")
            return None
        
        # Get first 5 product images
        image_urls = []
        for product in products[:10]:  # Check more products to get 5 images
            if product.get('images'):
                for img in product['images']:
                    if img.get('src') and len(image_urls) < 5:
                        image_urls.append(img['src'])
            if len(image_urls) >= 5:
                break
        
        # Get shop description from first product vendor or from homepage
        description = products[0].get('vendor', '') if products else ''
        
        return {
            'images': image_urls,
            'description': description,
            'source': 'shopify_api'
        }
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def scrape_etsy_apify(vendor):
    """Scrape Etsy store using Apify actor."""
    print(f"\n🎨 Scraping Etsy: {vendor['username']}")
    
    if not APIFY_TOKEN:
        print("  ❌ APIFY_TOKEN not set")
        return None
    
    shop_url = vendor['shop_url']
    
    # Start actor run
    actor_id = "epctex/etsy-scraper"
    run_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs"
    
    headers = {
        'Authorization': f'Bearer {APIFY_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Configure actor input
    input_data = {
        "startUrls": [{"url": shop_url}],
        "maxItems": 5,
        "endPage": 1,
        "extendOutputFunction": "",
        "proxy": {
            "useApifyProxy": True
        }
    }
    
    try:
        # Start run
        response = requests.post(run_url, json=input_data, headers=headers, timeout=30)
        response.raise_for_status()
        run_info = response.json()
        run_id = run_info['data']['id']
        
        print(f"  ⏳ Waiting for actor run {run_id}...")
        
        # Wait for run to complete (poll every 5 seconds, max 2 minutes)
        for _ in range(24):
            time.sleep(5)
            status_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs/{run_id}"
            status_response = requests.get(status_url, headers=headers)
            status_data = status_response.json()
            status = status_data['data']['status']
            
            if status == 'SUCCEEDED':
                # Get results
                dataset_id = status_data['data']['defaultDatasetId']
                results_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
                results_response = requests.get(results_url, headers=headers)
                results = results_response.json()
                
                # Extract images and description
                image_urls = []
                description = ""
                
                for item in results[:5]:
                    # Try to get shop description
                    if not description and item.get('shopDescription'):
                        description = item['shopDescription']
                    
                    # Get product images
                    if item.get('images'):
                        for img in item['images']:
                            if isinstance(img, str) and len(image_urls) < 5:
                                image_urls.append(img)
                            elif isinstance(img, dict) and img.get('url') and len(image_urls) < 5:
                                image_urls.append(img['url'])
                
                return {
                    'images': image_urls,
                    'description': description,
                    'source': 'etsy_apify'
                }
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                print(f"  ❌ Actor run {status}")
                return None
        
        print("  ⚠️  Timeout waiting for actor")
        return None
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def scrape_bigcartel_apify(vendor):
    """Scrape BigCartel store using Apify e-commerce tool."""
    print(f"\n🛒 Scraping BigCartel: {vendor['username']}")
    
    if not APIFY_TOKEN:
        print("  ❌ APIFY_TOKEN not set")
        return None
    
    shop_url = vendor['shop_url']
    
    # Start actor run
    actor_id = "apify/e-commerce-website-scraper"
    run_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs"
    
    headers = {
        'Authorization': f'Bearer {APIFY_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    input_data = {
        "startUrls": [{"url": shop_url}],
        "maxRequestsPerCrawl": 10,
        "proxy": {
            "useApifyProxy": True
        }
    }
    
    try:
        response = requests.post(run_url, json=input_data, headers=headers, timeout=30)
        response.raise_for_status()
        run_info = response.json()
        run_id = run_info['data']['id']
        
        print(f"  ⏳ Waiting for actor run {run_id}...")
        
        for _ in range(24):
            time.sleep(5)
            status_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs/{run_id}"
            status_response = requests.get(status_url, headers=headers)
            status_data = status_response.json()
            status = status_data['data']['status']
            
            if status == 'SUCCEEDED':
                dataset_id = status_data['data']['defaultDatasetId']
                results_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
                results_response = requests.get(results_url, headers=headers)
                results = results_response.json()
                
                image_urls = []
                description = ""
                
                for item in results[:10]:
                    if not description:
                        description = item.get('description', '') or item.get('about', '')
                    
                    # Extract images
                    if item.get('images'):
                        for img in item['images'][:5]:
                            if isinstance(img, str):
                                image_urls.append(img)
                            elif isinstance(img, dict) and img.get('url'):
                                image_urls.append(img['url'])
                    
                    if item.get('image') and len(image_urls) < 5:
                        image_urls.append(item['image'])
                    
                    if len(image_urls) >= 5:
                        break
                
                return {
                    'images': image_urls[:5],
                    'description': description,
                    'source': 'bigcartel_apify'
                }
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                print(f"  ❌ Actor run {status}")
                return None
        
        print("  ⚠️  Timeout waiting for actor")
        return None
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def scrape_custom_apify(vendor):
    """Scrape custom website using Apify Cheerio scraper."""
    print(f"\n🌐 Scraping custom site: {vendor['username']}")
    
    if not APIFY_TOKEN:
        print("  ❌ APIFY_TOKEN not set")
        return None
    
    shop_url = vendor['shop_url']
    
    # Try Cheerio scraper first (faster for static sites)
    actor_id = "apify/cheerio-scraper"
    run_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs"
    
    headers = {
        'Authorization': f'Bearer {APIFY_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Page function to extract images and description
    page_function = """
    async function pageFunction(context) {
        const $ = context.$;
        const images = [];
        
        // Find all images
        $('img').each((i, elem) => {
            const src = $(elem).attr('src') || $(elem).attr('data-src');
            if (src && !src.includes('icon') && !src.includes('logo')) {
                images.push(src);
            }
        });
        
        // Find description/about text
        const description = $('meta[name="description"]').attr('content') || 
                          $('.about').first().text() || 
                          $('.description').first().text() || 
                          $('p').first().text() || '';
        
        return {
            url: context.request.url,
            images: images.slice(0, 10),
            description: description.trim()
        };
    }
    """
    
    input_data = {
        "startUrls": [{"url": shop_url}],
        "maxRequestsPerCrawl": 3,
        "pageFunction": page_function,
        "proxy": {
            "useApifyProxy": True
        }
    }
    
    try:
        response = requests.post(run_url, json=input_data, headers=headers, timeout=30)
        response.raise_for_status()
        run_info = response.json()
        run_id = run_info['data']['id']
        
        print(f"  ⏳ Waiting for actor run {run_id}...")
        
        for _ in range(24):
            time.sleep(5)
            status_url = f"{APIFY_API_BASE}/acts/{actor_id}/runs/{run_id}"
            status_response = requests.get(status_url, headers=headers)
            status_data = status_response.json()
            status = status_data['data']['status']
            
            if status == 'SUCCEEDED':
                dataset_id = status_data['data']['defaultDatasetId']
                results_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
                results_response = requests.get(results_url, headers=headers)
                results = results_response.json()
                
                if results:
                    result = results[0]
                    image_urls = result.get('images', [])[:5]
                    description = result.get('description', '')
                    
                    return {
                        'images': image_urls,
                        'description': description,
                        'source': 'custom_cheerio'
                    }
                return None
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                print(f"  ❌ Actor run {status}")
                return None
        
        print("  ⚠️  Timeout waiting for actor")
        return None
        
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
        scrape_result = scrape_bigcartel_apify(vendor)
    elif 'depop.com' in shop_url:
        platform = "depop"
        print("  ⏭️  Skipping Depop (manual)")
        return None
    else:
        platform = "custom"
        scrape_result = scrape_custom_apify(vendor)
    
    if not scrape_result:
        return None
    
    # Create vendor image directory
    vendor_images_dir = IMAGES_DIR / vendor_slug
    vendor_images_dir.mkdir(exist_ok=True)
    
    # Download and resize images
    saved_images = []
    for i, img_url in enumerate(scrape_result['images'][:5]):
        output_path = vendor_images_dir / f"product_{i+1}.jpg"
        if download_and_resize_image(img_url, output_path):
            saved_images.append(str(output_path.relative_to(BASE_DIR)))
            print(f"  ✅ Saved image {i+1}/5")
    
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
    print(f"  📸 Downloaded {len(saved_images)}/5 images")
    
    return metadata


def main():
    """Main entry point."""
    print("🚀 Vendor Product Scraper - Phase 1 Test Run")
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
    
    # Save summary
    summary = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_processed': len(results),
        'results': results
    }
    
    summary_path = OUTPUT_DIR / f"test_run_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ Test run complete!")
    print(f"   Processed: {len(results)}/{len(test_vendors)} vendors")
    print(f"   Summary: {summary_path}")
    print(f"   Images: {IMAGES_DIR}")
    print(f"   Metadata: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
