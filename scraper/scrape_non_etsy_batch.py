"""
Non-Etsy vendor batch scraper.
Scrapes Shopify, BigCartel, and custom websites for product images and descriptions.
Skips Etsy and Depop vendors.
"""
import json
import csv
import time
import random
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

# Configuration
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "scraper" / "output"
VENDOR_CSV = BASE_DIR / "output" / "curated_vendors_final.csv"
OUTPUT_JSON = OUTPUT_DIR / "non_etsy_results.json"

OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

REQUEST_TIMEOUT = 15
RATE_LIMIT_MIN = 2.0
RATE_LIMIT_MAX = 3.0


def load_vendors():
    """Load vendors from CSV and filter out Etsy/Depop."""
    vendors = []
    with open(VENDOR_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            shop_url = row.get('shop_url', '').lower()
            # Skip Etsy and Depop
            if 'etsy.com' in shop_url or 'depop.com' in shop_url:
                continue
            # Skip Instagram-only vendors (no real shop_url)
            if not shop_url or 'instagram.com' in shop_url:
                continue
            vendors.append(row)
    return vendors


def detect_platform(shop_url):
    """Detect vendor platform."""
    url_lower = shop_url.lower()
    if 'shopify' in url_lower or 'myshopify' in url_lower:
        return 'shopify'
    elif 'bigcartel' in url_lower:
        return 'bigcartel'
    else:
        return 'custom'


def scrape_shopify(shop_url):
    """Scrape Shopify store via products.json API."""
    try:
        parsed = urlparse(shop_url)
        domain = parsed.netloc
        if not domain:
            # Handle URLs without protocol
            domain = shop_url.split('/')[0]
        
        products_url = f"https://{domain}/products.json"
        
        response = requests.get(products_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        products = data.get('products', [])
        if not products:
            return None, None, None
        
        # Collect product images
        image_urls = []
        for product in products[:10]:
            if product.get('images'):
                for img in product['images']:
                    src = img.get('src')
                    if src and len(image_urls) < 3:
                        # Remove size parameters for original quality
                        src = src.split('?')[0]
                        image_urls.append(src)
            if len(image_urls) >= 3:
                break
        
        # Get store name and description
        store_name = products[0].get('vendor', '') if products else ''
        
        # Try to get shop description from main page
        description = ''
        try:
            main_response = requests.get(shop_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            main_response.raise_for_status()
            soup = BeautifulSoup(main_response.content, 'html.parser')
            
            meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
            if meta_desc:
                description = meta_desc.get('content', '')
        except:
            pass
        
        return store_name, description, image_urls
        
    except Exception as e:
        return None, None, None


def scrape_bigcartel(shop_url):
    """Scrape BigCartel store via HTML."""
    try:
        response = requests.get(shop_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get store name
        store_name = ''
        title_tag = soup.find('title')
        if title_tag:
            store_name = title_tag.text.strip()
        
        # Get description
        description = ''
        meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content', '')
        
        # Get product images
        image_urls = []
        
        # BigCartel specific selectors
        product_images = soup.select('img.product-image, .product img, .item img')
        for img in product_images:
            src = img.get('data-src') or img.get('src')
            if src:
                # Handle relative URLs
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(shop_url, src)
                elif not src.startswith('http'):
                    src = urljoin(shop_url, src)
                
                # Skip tiny images
                if 'thumb' in src.lower() or '_small' in src.lower():
                    continue
                
                if src not in image_urls and len(image_urls) < 3:
                    image_urls.append(src)
        
        # Fallback: any reasonable-sized image
        if len(image_urls) < 3:
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src')
                if not src:
                    continue
                
                # Skip common non-product images
                if any(skip in src.lower() for skip in ['logo', 'icon', 'favicon', 'avatar', 'profile', 'banner']):
                    continue
                
                # Handle relative URLs
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(shop_url, src)
                elif not src.startswith('http'):
                    src = urljoin(shop_url, src)
                
                if src not in image_urls and len(image_urls) < 3:
                    image_urls.append(src)
        
        return store_name, description, image_urls
        
    except Exception as e:
        return None, None, None


def scrape_custom(shop_url):
    """Scrape custom website via HTML."""
    try:
        response = requests.get(shop_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get store name
        store_name = ''
        og_site_name = soup.find('meta', {'property': 'og:site_name'})
        if og_site_name:
            store_name = og_site_name.get('content', '')
        if not store_name:
            title_tag = soup.find('title')
            if title_tag:
                store_name = title_tag.text.strip()
        
        # Get description
        description = ''
        meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content', '')
        
        # Try to find about/description section
        if not description:
            about_section = soup.find(['div', 'section'], class_=lambda c: c and ('about' in c.lower() or 'description' in c.lower()))
            if about_section:
                description = about_section.get_text(strip=True)[:500]
        
        # Get product images
        image_urls = []
        
        # Look for product images with common selectors
        product_selectors = [
            'img.product-image',
            'img[alt*="product"]',
            '.product img',
            '.item img',
            '.gallery img',
            'img[src*="product"]',
            'img[src*="item"]'
        ]
        
        for selector in product_selectors:
            for img in soup.select(selector):
                src = img.get('data-src') or img.get('src')
                if src:
                    # Handle relative URLs
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(shop_url, src)
                    elif not src.startswith('http'):
                        src = urljoin(shop_url, src)
                    
                    if src not in image_urls and len(image_urls) < 3:
                        image_urls.append(src)
            
            if len(image_urls) >= 3:
                break
        
        # Fallback: any image that looks like a product
        if len(image_urls) < 3:
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src')
                if not src:
                    continue
                
                # Skip common non-product images
                if any(skip in src.lower() for skip in ['logo', 'icon', 'favicon', 'avatar', 'profile', 'banner', 'header']):
                    continue
                
                # Prefer images with "product" or "shop" in path
                priority = 'product' in src.lower() or 'shop' in src.lower() or 'item' in src.lower()
                
                # Handle relative URLs
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(shop_url, src)
                elif not src.startswith('http'):
                    src = urljoin(shop_url, src)
                
                if src not in image_urls:
                    if priority:
                        image_urls.insert(0, src)
                    else:
                        image_urls.append(src)
                    
                    if len(image_urls) >= 3:
                        break
        
        return store_name, description, image_urls[:3]
        
    except Exception as e:
        return None, None, None


def scrape_vendor(vendor):
    """Scrape a single vendor."""
    username = vendor['username']
    shop_url = vendor['shop_url']
    
    # Detect platform
    platform = detect_platform(shop_url)
    
    # Scrape based on platform
    if platform == 'shopify':
        store_name, description, image_urls = scrape_shopify(shop_url)
    elif platform == 'bigcartel':
        store_name, description, image_urls = scrape_bigcartel(shop_url)
    else:
        store_name, description, image_urls = scrape_custom(shop_url)
    
    # Determine status
    status = 'failed'
    error = None
    
    if store_name or description or image_urls:
        if image_urls and len(image_urls) >= 2:
            status = 'success'
        elif image_urls or description:
            status = 'partial'
    else:
        error = 'No data extracted'
    
    # Use display_name if no store_name found
    if not store_name:
        store_name = vendor.get('display_name', username)
    
    # Use display_description if no description found
    if not description:
        description = vendor.get('display_description', '')
    
    return {
        'username': username,
        'store_name': store_name,
        'shop_url': shop_url,
        'platform': platform,
        'description': description,
        'product_images': image_urls if image_urls else [],
        'status': status,
        'error': error
    }


def main():
    """Main entry point."""
    print("=" * 70)
    print("🚀 NON-ETSY VENDOR BATCH SCRAPER")
    print("=" * 70)
    
    # Load vendors
    print(f"\n📂 Loading vendors from: {VENDOR_CSV.name}")
    vendors = load_vendors()
    total = len(vendors)
    print(f"✅ Loaded {total} non-Etsy/Depop vendors")
    
    # Process vendors
    results = []
    success_count = 0
    partial_count = 0
    failed_count = 0
    
    print(f"\n🔄 Starting scrape...\n")
    
    for idx, vendor in enumerate(vendors, 1):
        username = vendor['username']
        
        try:
            result = scrape_vendor(vendor)
            results.append(result)
            
            # Update counts
            if result['status'] == 'success':
                success_count += 1
                emoji = "✅"
            elif result['status'] == 'partial':
                partial_count += 1
                emoji = "⚠️"
            else:
                failed_count += 1
                emoji = "❌"
            
            # Progress output
            img_count = len(result['product_images'])
            platform = result['platform']
            print(f"[{idx}/{total}] {emoji} {username}: {img_count} images | {platform}")
            
        except Exception as e:
            # Handle unexpected errors
            failed_count += 1
            results.append({
                'username': username,
                'store_name': vendor.get('display_name', username),
                'shop_url': vendor.get('shop_url', ''),
                'platform': 'unknown',
                'description': '',
                'product_images': [],
                'status': 'failed',
                'error': str(e)
            })
            print(f"[{idx}/{total}] ❌ {username}: ERROR - {str(e)[:50]}")
        
        # Rate limiting
        if idx < total:  # Don't wait after last vendor
            time.sleep(random.uniform(RATE_LIMIT_MIN, RATE_LIMIT_MAX))
    
    # Save results
    print(f"\n💾 Saving results to: {OUTPUT_JSON.name}")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print(f"\n" + "=" * 70)
    print(f"✅ BATCH SCRAPE COMPLETE")
    print(f"=" * 70)
    print(f"📊 Summary:")
    print(f"   Total vendors:    {total}")
    print(f"   ✅ Success:       {success_count} ({success_count/total*100:.1f}%)")
    print(f"   ⚠️  Partial:       {partial_count} ({partial_count/total*100:.1f}%)")
    print(f"   ❌ Failed:        {failed_count} ({failed_count/total*100:.1f}%)")
    print(f"\n💾 Output: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
