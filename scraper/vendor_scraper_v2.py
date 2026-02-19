"""
Enhanced vendor product scraping pipeline with:
1. Deeper page scraping (not just homepage)
2. Image validation & filtering (size, content type, junk patterns)
3. Instagram fallback for empty/filtered results
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

# Image validation patterns (junk keywords to skip)
JUNK_PATTERNS = [
    'icon', 'logo', 'social', 'facebook', 'instagram', 'twitter', 
    'pinterest', 'payment', 'badge', 'sprite', 'favicon', 'avatar',
    'profile', 'placeholder', 'loading', 'button', 'arrow', 'cart',
    'menu', 'nav', 'header', 'footer', 'banner'
]

def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


def is_valid_image_url(url):
    """Check if URL looks like a valid product image."""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Skip SVGs (usually icons)
    if url_lower.endswith('.svg'):
        return False
    
    # Skip if contains junk patterns
    for pattern in JUNK_PATTERNS:
        if pattern in url_lower:
            return False
    
    # Skip known social CDNs
    social_cdns = ['facebook.com', 'twitter.com', 'instagram.com/static', 
                   'pinterest.com', 'addtoany.com', 'sharethis.com']
    for cdn in social_cdns:
        if cdn in url_lower:
            return False
    
    return True


def validate_image_dimensions(url, min_size=100):
    """
    Check image dimensions via HEAD request if possible.
    Returns True if image is valid (>= min_size x min_size), False otherwise.
    """
    try:
        # Try HEAD request first (faster)
        response = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        
        # Check content type
        content_type = response.headers.get('Content-Type', '').lower()
        if not content_type.startswith('image/'):
            return False
        
        # Try to get content-length
        content_length = response.headers.get('Content-Length')
        if content_length:
            # Skip very small files (< 5KB likely icons)
            if int(content_length) < 5000:
                return False
        
        # For more accurate check, download and check dimensions
        # But only for a sample to avoid too many requests
        return True
        
    except Exception:
        # If HEAD fails, assume it's okay (we'll filter in download phase)
        return True


def download_and_resize_image(url, output_path, max_width=800):
    """Download an image, validate dimensions, and resize."""
    try:
        if url.startswith('//'):
            url = 'https:' + url
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        
        # Validate dimensions (skip small images)
        if img.width < 100 or img.height < 100:
            print(f"⚠️ Too small ({img.width}x{img.height})")
            return False
        
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
        print(f"❌ {str(e)[:40]}")
        return False


def scrape_shopify_deep(vendor):
    """
    Enhanced Shopify scraper.
    Try /products.json AND /collections/all for more products.
    """
    shop_url = vendor['shop_url']
    domain = urlparse(shop_url).netloc
    
    image_urls = []
    description = ""
    
    # Method 1: /products.json
    try:
        products_url = f"https://{domain}/products.json"
        response = requests.get(products_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        products = data.get('products', [])
        for product in products[:15]:
            if product.get('images'):
                for img in product['images']:
                    src = img.get('src')
                    if src and is_valid_image_url(src):
                        if src not in image_urls:
                            image_urls.append(src)
                        if len(image_urls) >= 10:
                            break
            if len(image_urls) >= 10:
                break
        
        if products and not description:
            description = products[0].get('vendor', '')
    except Exception as e:
        print(f"  ⚠️ /products.json failed: {e}")
    
    # Method 2: Try /collections/all (HTML scrape)
    if len(image_urls) < 5:
        try:
            collections_url = f"https://{domain}/collections/all"
            response = requests.get(collections_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for product images
            img_tags = soup.find_all('img', src=True)
            for img in img_tags:
                src = img.get('data-src') or img.get('src')
                if src and is_valid_image_url(src):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = f"https://{domain}{src}"
                    
                    if src not in image_urls:
                        image_urls.append(src)
                    if len(image_urls) >= 10:
                        break
        except Exception as e:
            print(f"  ⚠️ /collections/all failed: {e}")
    
    if not image_urls:
        return None
    
    return {
        'images': image_urls[:10],
        'description': description,
        'source': 'shopify_deep'
    }


def scrape_bigcartel_deep(vendor):
    """
    Enhanced BigCartel scraper.
    Try homepage AND /products page.
    """
    shop_url = vendor['shop_url']
    domain = urlparse(shop_url).netloc
    
    image_urls = []
    description = ""
    
    # Try /products page first
    urls_to_try = [
        f"{shop_url.rstrip('/')}/products",
        shop_url
    ]
    
    for url in urls_to_try:
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get description
            if not description:
                meta_desc = soup.find('meta', {'name': 'description'})
                if meta_desc:
                    description = meta_desc.get('content', '')
            
            # Find product images
            img_tags = soup.find_all('img', src=True)
            for img in img_tags:
                src = img.get('data-src') or img.get('src')
                if src and is_valid_image_url(src):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(url, src)
                    
                    if src not in image_urls:
                        image_urls.append(src)
                    if len(image_urls) >= 10:
                        break
            
            if len(image_urls) >= 5:
                break
                
        except Exception as e:
            print(f"  ⚠️ {url} failed: {e}")
            continue
    
    if not image_urls:
        return None
    
    return {
        'images': image_urls[:10],
        'description': description,
        'source': 'bigcartel_deep'
    }


def scrape_custom_deep(vendor):
    """
    Enhanced custom site scraper.
    Try homepage AND common product paths.
    """
    shop_url = vendor['shop_url']
    
    # Common product page paths
    paths_to_try = [
        '/shop',
        '/products',
        '/collections',
        '/store',
        '/catalog',
        '/gallery',
        ''  # homepage last
    ]
    
    image_urls = []
    description = ""
    
    for path in paths_to_try:
        url = f"{shop_url.rstrip('/')}{path}"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get description
            if not description:
                meta_desc = soup.find('meta', {'name': 'description'}) or \
                           soup.find('meta', {'property': 'og:description'})
                if meta_desc:
                    description = meta_desc.get('content', '')
            
            # Find images
            img_tags = soup.find_all('img', src=True)
            for img in img_tags:
                src = img.get('data-src') or img.get('src')
                if src and is_valid_image_url(src):
                    # Handle relative URLs
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(url, src)
                    elif not src.startswith('http'):
                        src = urljoin(url, src)
                    
                    if src not in image_urls:
                        image_urls.append(src)
                    if len(image_urls) >= 10:
                        break
            
            if len(image_urls) >= 5:
                break
                
        except Exception:
            continue
    
    if not image_urls:
        return None
    
    return {
        'images': image_urls[:10],
        'description': description,
        'source': 'custom_deep'
    }


def scrape_etsy_instagram(vendor, instagram_images):
    """Use Instagram images for Etsy vendors."""
    username = vendor['username']
    
    # Try with and without underscore prefix
    images = instagram_images.get(username) or instagram_images.get(f"_{username}")
    
    if not images:
        return None
    
    description = vendor.get('bio', '')
    
    return {
        'images': images[:5],
        'description': description,
        'source': 'etsy_instagram'
    }


def apply_instagram_fallback(vendor, instagram_images):
    """
    Apply Instagram fallback for vendors with no product images.
    Returns Instagram image URLs if available.
    """
    username = vendor['username']
    
    # Try multiple username variations
    variations = [
        username,
        f"_{username}",
        username.replace('_', ''),
        username.replace('-', '_')
    ]
    
    for variant in variations:
        images = instagram_images.get(variant)
        if images:
            print(f"  📸 Instagram fallback: {len(images)} images found")
            return images[:5]
    
    return None


def process_vendor(vendor, instagram_images):
    """Process a single vendor with enhanced scraping."""
    username = vendor['username']
    shop_url = vendor.get('shop_url', '').lower()
    vendor_slug = slugify(username)
    
    print(f"\n{'='*60}")
    print(f"📦 {username}")
    print(f"🔗 {shop_url[:70]}...")
    
    if not shop_url:
        print("⏭️ No shop URL")
        return None
    
    # Determine platform and scrape
    scrape_result = None
    platform = "unknown"
    
    if 'shopify' in shop_url or 'myshopify' in shop_url:
        platform = "shopify"
        print("🛍️ Shopify → Deep scrape (products.json + collections)")
        scrape_result = scrape_shopify_deep(vendor)
    elif 'etsy.com' in shop_url:
        platform = "etsy"
        print("🎨 Etsy → Instagram images")
        scrape_result = scrape_etsy_instagram(vendor, instagram_images)
    elif 'bigcartel' in shop_url:
        platform = "bigcartel"
        print("🛒 BigCartel → Deep scrape (products page)")
        scrape_result = scrape_bigcartel_deep(vendor)
    elif 'depop.com' in shop_url:
        platform = "depop"
        print("⏭️ Depop → Skip (manual)")
        return None
    else:
        platform = "custom"
        print("🌐 Custom → Deep scrape (shop/products/collections)")
        scrape_result = scrape_custom_deep(vendor)
    
    # Apply Instagram fallback if no images found
    if not scrape_result or not scrape_result.get('images'):
        print("  ⚠️ No product images found, trying Instagram fallback...")
        instagram_imgs = apply_instagram_fallback(vendor, instagram_images)
        if instagram_imgs:
            scrape_result = {
                'images': instagram_imgs,
                'description': vendor.get('bio', ''),
                'source': 'instagram_fallback'
            }
        else:
            print("  ❌ No Instagram fallback available")
            return None
    
    # Filter and validate images
    print(f"  🔍 Validating {len(scrape_result['images'])} images...")
    validated_images = []
    for img_url in scrape_result['images']:
        if is_valid_image_url(img_url) and validate_image_dimensions(img_url):
            validated_images.append(img_url)
        if len(validated_images) >= 5:
            break
    
    if not validated_images:
        print("  ❌ All images filtered out")
        # Last resort: try Instagram fallback
        instagram_imgs = apply_instagram_fallback(vendor, instagram_images)
        if instagram_imgs:
            validated_images = instagram_imgs
            scrape_result['source'] = 'instagram_fallback'
        else:
            return None
    
    print(f"  ✅ {len(validated_images)} valid images")
    
    # Download and resize images
    vendor_images_dir = IMAGES_DIR / vendor_slug
    vendor_images_dir.mkdir(exist_ok=True)
    
    saved_images = []
    print(f"  📥 Downloading: ", end='')
    for i, img_url in enumerate(validated_images[:5]):
        output_path = vendor_images_dir / f"product_{i+1}.jpg"
        if download_and_resize_image(img_url, output_path):
            saved_images.append(str(output_path.relative_to(BASE_DIR)))
            print("✓", end='', flush=True)
        else:
            print("✗", end='', flush=True)
    print(f" ({len(saved_images)}/5)")
    
    if not saved_images:
        print("  ❌ Download failed")
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
    
    print(f"  💾 Metadata saved: {metadata_path.name}")
    return metadata


def main():
    """Main entry point."""
    print("="*60)
    print("🚀 ENHANCED VENDOR SCRAPER V2")
    print("   - Deeper page scraping")
    print("   - Image validation & filtering")
    print("   - Instagram fallback")
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
    
    # Filter to non-Etsy, non-Depop vendors
    non_etsy_vendors = platforms['shopify'] + platforms['bigcartel'] + platforms['custom']
    print(f"\n🎯 Target: {len(non_etsy_vendors)} non-Etsy/non-Depop vendors")
    
    # Process all vendors
    results = []
    failed = []
    
    for i, vendor in enumerate(non_etsy_vendors, 1):
        print(f"\n[{i}/{len(non_etsy_vendors)}]", end=' ')
        try:
            result = process_vendor(vendor, instagram_images)
            if result:
                results.append(result)
            else:
                failed.append(vendor['username'])
        except Exception as e:
            print(f"  ❌ Fatal error: {e}")
            failed.append(vendor['username'])
        
        # Rate limiting
        time.sleep(0.5)
    
    # Save results
    output_file = OUTPUT_DIR / "non_etsy_results_v2.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save summary
    summary = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_attempted': len(non_etsy_vendors),
        'successful': len(results),
        'failed': len(failed),
        'success_rate': f"{len(results)}/{len(non_etsy_vendors)} ({100*len(results)//len(non_etsy_vendors)}%)",
        'failed_vendors': failed[:20],  # First 20 failures
        'source_breakdown': {}
    }
    
    # Count by source
    for r in results:
        source = r.get('source', 'unknown')
        summary['source_breakdown'][source] = summary['source_breakdown'].get(source, 0) + 1
    
    summary_file = OUTPUT_DIR / "scrape_v2_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"📊 Success: {len(results)}/{len(non_etsy_vendors)} ({100*len(results)//max(len(non_etsy_vendors),1)}%)")
    print(f"💾 Results: {output_file.name}")
    print(f"📁 Images: {IMAGES_DIR}")
    print(f"\n📋 Source Breakdown:")
    for source, count in sorted(summary['source_breakdown'].items()):
        print(f"   {source.ljust(25)} {count:3d}")
    
    if failed:
        print(f"\n⚠️  {len(failed)} vendors failed (see {summary_file.name})")


if __name__ == "__main__":
    main()
