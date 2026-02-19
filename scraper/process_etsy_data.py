#!/usr/bin/env python3
"""
Process Etsy scrape data and update festival vendor website.
"""

import json
from collections import defaultdict
from pathlib import Path
import re

# Mapping from Etsy seller names to vendor IDs (from vendors.json)
SELLER_TO_VENDOR_ID = {
    'EtherealAdornmentsUS': 'etherealadornmentsdesign',
    'CosmicFantasyStore': 'cosmicfantasystore',
    'ShambannieCreations': 'shambannie_creations',
    'Boogiedowndyes': 'boogiedowndyes',
    'MindfullMatters': 'mindfulldesign.co',
    'scopermonstar': 'scopermonstar',
    'LunarSolDesignsShop': 'lunarsoldesigns',
    'VerdessaFairy': 'verdessa_fairy',
    'StoneSparrowCrochet': 'stonesparrowthreads',
    'Littlechaoscave': 'littlechaoscavecrochet',
    'SleepyMoonPlush': 'texturejester',
    'SurrealismTieDye': 'maximilian_tie_dye',
    'WeavingWizardDesigns': 'weaving_wizard_designs',
    'AquaMoon1111': 'aquamoon1111',
    'KandiBeanCo': 'kandi.bean.co',
    'RichMahoganyLife': 'rml.designs',
    'Solunaceae': 'solunaceae',
    'CARRIEAFShop': 'carrieaf_',
    'tinkercast': 'tinkercast.official',
    'WookandFairy': 'wook_and_fairy',
    'VastillioandCasta': 'vastillioandcasta',
    'FunktionsOfNature': 'funktionsofnature',
    'BrasByNicolle': 'nicolleg308',
    'Kcullenthats': 'kcullenthats',
    'Mysticloak': 'mysticloak',
    'AvaJeida': 'faelienz',
    'WearReveal': 'wearreveal',
    'DeadTreeTextiles': 'deadtreetextiles'
}

def load_json(path):
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    """Save JSON file with nice formatting."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def group_by_seller(products):
    """Group products by seller name."""
    sellers = defaultdict(list)
    for product in products:
        seller_name = product.get('seller', {}).get('name')
        if seller_name:
            sellers[seller_name].append(product)
    return dict(sellers)

def select_diverse_products(products, count=3):
    """Select diverse products (different names/types)."""
    # Remove products with very similar names
    selected = []
    seen_names = set()
    
    for product in products:
        name = product.get('name', '').lower()
        # Create a simplified name for comparison
        simple_name = re.sub(r'[^a-z0-9\s]', '', name)
        words = set(simple_name.split())
        
        # Check if this is significantly different from already selected
        is_unique = True
        for seen_words in seen_names:
            # If more than 50% of words overlap, consider it similar
            overlap = len(words & seen_words) / max(len(words), len(seen_words))
            if overlap > 0.5:
                is_unique = False
                break
        
        if is_unique:
            selected.append(product)
            seen_names.add(frozenset(words))
            
            if len(selected) >= count:
                break
    
    return selected

def generate_bio(products):
    """Generate a short bio (15-25 words) from product names and descriptions."""
    # Collect keywords from products
    keywords = []
    for product in products[:5]:  # Look at first 5 products
        name = product.get('name', '')
        desc = product.get('descriptionHTML', '') or product.get('description', '')
        
        # Extract key product types/themes
        text = (name + ' ' + desc).lower()
        
        # Common product type keywords
        types = [
            'dreadlocks', 'braids', 'earrings', 'ears', 'wings', 'crown', 'headdress',
            'hood', 'coat', 'jacket', 'vest', 'top', 'crop top', 'bell bottom', 'pants',
            'tie-dye', 'tie dye', 'crochet', 'hand-dyed', 'handmade', 'hand-braided',
            'festival', 'rave', 'cosplay', 'fairy', 'festival wear', 'rave wear',
            'bucket hat', 'hat', 'parasol', 'umbrella', 'bag', 'tote', 'fanny pack',
            'necklace', 'jewelry', 'ring', 'bracelet', 'pendant',
            'plush', 'plushie', 'stuffed animal', 'toy',
            'patchwork', 'upcycled', 'sustainable', 'one-of-a-kind', 'OOAK',
            'psychedelic', 'trippy', 'holographic', 'iridescent', 'LED',
            'faux fur', 'feathers', 'crystal', 'beaded',
            'painting', 'art print', 'poster', 'sticker',
            'pattern', 'tutorial', 'PDF',
            'dress', 'romper', 'bodysuit', 'harness', 'bra', 'bikini',
            'shoes', 'boots', 'sandals',
            'mask', 'goggles', 'sunglasses',
            'cloak', 'cape', 'shawl', 'scarf', 'pashmina'
        ]
        
        for keyword in types:
            if keyword in text and keyword not in keywords:
                keywords.append(keyword)
                if len(keywords) >= 4:
                    break
        
        if len(keywords) >= 4:
            break
    
    # Generate bio based on keywords
    seller_name = products[0].get('seller', {}).get('name', 'Artist')
    
    # Create descriptive phrases
    if not keywords:
        return f"Handmade festival clothing and accessories by {seller_name}."
    
    # Build natural, specific descriptions
    if not keywords:
        return "Handmade festival clothing and accessories."
    
    # Pattern-based bio generation for more natural language
    if 'tie-dye' in keywords or 'tie dye' in keywords:
        other = [k for k in keywords if k not in ['tie-dye', 'tie dye', 'handmade']][:2]
        if 'top' in other or 'crop top' in other:
            bio = "Vibrant hand-dyed tie-dye crop tops, bell bottoms, and matching festival sets."
        elif other:
            bio = f"Hand-dyed tie-dye {', '.join(other)} for festivals, raves, and hippie vibes."
        else:
            bio = "Colorful hand-dyed tie-dye clothing for festivals and psychedelic style."
    
    elif 'crochet' in keywords:
        other = [k for k in keywords if k not in ['crochet', 'handmade']][:2]
        if 'top' in other or 'vest' in other or 'festival' in other:
            bio = "Handmade crochet festival tops, vests, and accessories for raves and bohemian style."
        elif other:
            bio = f"Custom crochet {', '.join(other)} for festivals, raves, and alternative fashion."
        else:
            bio = "Handcrafted crochet festival clothing and accessories for bohemian style."
    
    elif 'dreadlocks' in keywords or 'braids' in keywords:
        types = []
        if 'dreadlocks' in keywords:
            types.append('dreadlocks')
        if 'braids' in keywords:
            types.append('braids')
        bio = f"Handcrafted synthetic {', '.join(types)} and hair extensions for festivals, raves, and cosplay."
    
    elif 'patchwork' in keywords or 'upcycled' in keywords:
        other = [k for k in keywords if k not in ['patchwork', 'upcycled', 'handmade']][:2]
        if 'hood' in other or 'coat' in other or 'jacket' in other:
            bio = "One-of-a-kind upcycled patchwork hoods, coats, and wearable art for festival fashion."
        else:
            bio = f"Sustainable upcycled patchwork {', '.join(other or ['clothing'])} and unique festival wear."
    
    elif any(x in keywords for x in ['ears', 'wings', 'crown', 'headdress', 'tail']):
        items = [k for k in keywords if k in ['ears', 'wings', 'crown', 'headdress', 'tail', 'fairy']][:3]
        if 'ears' in items:
            bio = "Handmade faux fur animal ears, paws, and tails for festivals, cosplay, and raves."
        elif 'wings' in items or 'crown' in items:
            bio = "Enchanted fairy wings, forest crowns, and magical headdresses for festival fantasies."
        else:
            bio = f"Handcrafted fantasy {', '.join(items)} for festivals, cosplay, and alternative style."
    
    elif 'bucket hat' in keywords or 'hat' in keywords:
        bio = "Unique patchwork bucket hats, psychedelic hoods, and festival headwear."
    
    elif 'parasol' in keywords or 'umbrella' in keywords:
        bio = "One-of-a-kind handmade festival parasols with fringe, butterflies, and LED fairy lights."
    
    elif 'jewelry' in keywords or 'necklace' in keywords or 'pendant' in keywords:
        if 'wire wrap' in keywords or 'crystal' in keywords:
            bio = "Mystic wire-wrapped crystal necklaces, pendants, and healing gemstone jewelry."
        else:
            bio = "Handmade artisan jewelry with crystals, beads, and natural stones for festival style."
    
    elif 'plush' in keywords or 'plushie' in keywords or 'stuffed animal' in keywords:
        bio = "Handmade custom plush creatures, stuffed animals, and one-of-a-kind fuzzy friends."
    
    elif 'pattern' in keywords or 'PDF' in keywords or 'tutorial' in keywords:
        if 'crochet' in keywords:
            bio = "Crochet patterns and tutorials for festival clothing, bags, and unique bohemian accessories."
        else:
            bio = "Downloadable patterns and sewing tutorials for handmade festival clothing and accessories."
    
    elif 'sticker' in keywords or 'art print' in keywords or 'poster' in keywords:
        bio = "Psychedelic art prints, trippy stickers, and visionary artwork for festival lovers."
    
    elif 'hood' in keywords or 'coat' in keywords:
        bio = "Handmade patchwork festival hoods, faux fur coats, and wearable art outerwear."
    
    elif any(x in keywords for x in ['top', 'crop top', 'vest', 'jacket', 'pants', 'bell bottom']):
        items = [k for k in keywords if k in ['top', 'crop top', 'vest', 'jacket', 'pants', 'bell bottom', 'dress', 'romper']][:3]
        bio = f"Handmade festival {', '.join(items)} and alternative clothing for raves and bohemian style."
    
    else:
        # Generic fallback with best keywords
        items = ', '.join(keywords[:3])
        bio = f"Handmade {items} for festivals, raves, and alternative fashion."
    
    return bio

def find_vendor_by_instagram(vendors, instagram_username):
    """Find a vendor in vendors.json by Instagram username."""
    for vendor in vendors:
        if vendor.get('username') == instagram_username or vendor.get('id') == instagram_username:
            return vendor
    return None

def main():
    # Paths
    base_dir = Path('/home/bumby/.openclaw/workspace/festival-vendors')
    etsy_data_path = base_dir / 'scraper' / 'output' / 'etsy_scrape_raw.json'
    vendors_path = base_dir / 'website' / 'vendors.json'
    
    print("Loading Etsy data...")
    etsy_products = load_json(etsy_data_path)
    print(f"Loaded {len(etsy_products)} products")
    
    print("\nLoading vendors.json...")
    vendors_data = load_json(vendors_path)
    vendors = vendors_data['vendors']
    print(f"Loaded {len(vendors)} vendors")
    
    # Group products by seller
    print("\nGrouping products by seller...")
    sellers = group_by_seller(etsy_products)
    print(f"Found {len(sellers)} unique sellers")
    
    # Process each seller
    matched_count = 0
    unmatched_sellers = []
    updates = []
    
    for seller_name, products in sellers.items():
        # Find vendor ID
        vendor_id = SELLER_TO_VENDOR_ID.get(seller_name)
        
        if not vendor_id:
            unmatched_sellers.append(seller_name)
            continue
        
        # Find vendor in vendors.json
        vendor = find_vendor_by_instagram(vendors, vendor_id)
        
        if not vendor:
            print(f"  ⚠️  Vendor not found in vendors.json: {vendor_id} ({seller_name})")
            unmatched_sellers.append(seller_name)
            continue
        
        # Select 3 diverse products
        selected_products = select_diverse_products(products, 3)
        
        # Extract first image from each product
        product_images = []
        for product in selected_products:
            images = product.get('images', [])
            if images:
                # Get the first image (il_794xN thumbnail)
                product_images.append(images[0])
        
        # Generate bio
        bio = generate_bio(products)
        
        # Update vendor (use 'images' field name to match existing website code)
        vendor['bio'] = bio
        vendor['images'] = product_images
        
        matched_count += 1
        updates.append({
            'seller': seller_name,
            'vendor_id': vendor_id,
            'username': vendor.get('username', vendor_id),
            'bio': bio,
            'images': len(product_images),
            'sample_products': [p.get('name', '')[:50] for p in selected_products[:2]]
        })
    
    # Save updated vendors.json
    print(f"\n✅ Matched and updated {matched_count} vendors")
    print(f"\n💾 Saving vendors.json...")
    save_json(vendors_path, vendors_data)
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"  - Total Etsy sellers: {len(sellers)}")
    print(f"  - Matched vendors: {matched_count}")
    print(f"  - Unmatched sellers: {len(unmatched_sellers)}")
    
    if unmatched_sellers:
        print(f"\n⚠️  Unmatched sellers:")
        for seller in unmatched_sellers:
            print(f"    - {seller}")
    
    print(f"\n📝 Sample updates:")
    for update in updates[:5]:
        print(f"\n  {update['seller']} → @{update['username']} ({update['vendor_id']})")
        print(f"    Bio: {update['bio']}")
        print(f"    Images: {update['images']}")
        print(f"    Sample products:")
        for prod in update['sample_products']:
            print(f"      • {prod}")
    
    if len(updates) > 5:
        print(f"\n  ... and {len(updates) - 5} more")
    
    print("\n✨ Done!")

if __name__ == '__main__':
    main()
