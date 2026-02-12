"""
Configuration for the festival vendor curation pipeline.
All tunables live here — thresholds, keywords, API settings, categories.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# DeepSeek API
# =============================================================================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"  # DeepSeek-V3, cheapest capable model
LLM_BATCH_SIZE = 10  # Records per API call (batching saves tokens)
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 5  # seconds
LLM_TIMEOUT = 60  # seconds per request

# =============================================================================
# Rules Engine Thresholds
# =============================================================================

# Follower count boundaries
# Too many followers = likely big brand. Too few = likely personal account.
MIN_FOLLOWERS = 200
MAX_FOLLOWERS = 500_000  # Above this, almost certainly a big brand
BIG_BRAND_FOLLOWER_THRESHOLD = 100_000  # High confidence big brand

# Following-to-follower ratio
# Real small businesses: moderate ratio. Personal accounts: high ratio.
MAX_FOLLOWING_RATIO = 5.0  # following/followers — personal accounts follow tons

# Confidence score thresholds for rules engine
RULES_YES_THRESHOLD = 0.70   # Above this → auto-YES (skip LLM)
RULES_NO_THRESHOLD = 0.25    # Below this → auto-NO (skip LLM)
# Between these two → MAYBE → sent to LLM

# Final inclusion threshold (after LLM scoring)
FINAL_INCLUSION_THRESHOLD = 0.55

# =============================================================================
# Keyword Lists (case-insensitive matching against bio + website descriptions)
# =============================================================================

# Strong positive signals — handmade/unique/creative small businesses
STRONG_YES_KEYWORDS = [
    "handmade", "hand made", "hand-made", "handcrafted", "hand crafted",
    "one of a kind", "ooak", "one-of-a-kind",
    "small batch", "made to order", "custom order", "custom made",
    "artist", "artisan", "maker", "creator", "designer",
    "fiber art", "wearable art", "functional art",
    "psychedelic", "trippy", "tie dye", "tie-dye", "tiedye",
    "festival wear", "festival fashion", "festival clothing",
    "rave wear", "plur", "kandi",
    "resin art", "epoxy", "polymer clay",
    "macrame", "crochet", "knit", "sewn", "sewing",
    "beaded", "beadwork", "hand beaded",
    "woodwork", "leather craft", "metalwork",
    "crystal", "gemstone", "healing stones",
    "etsy.com/shop", "bigcartel.com", "storenvy.com",
    "dm for custom", "dm for orders", "commissions open",
    "shop link in bio", "shop now", "new drop",
    "one offs", "limited run", "small business",
]

# Weak positive signals — suggestive but not definitive
WEAK_YES_KEYWORDS = [
    "art", "creative", "design", "studio",
    "boho", "bohemian", "vintage", "retro",
    "spiritual", "metaphysical", "mystical",
    "mushroom", "sacred geometry",
    "festival", "rave", "burning man", "playa",
    "colorful", "colourful", "vibrant", "neon",
    "unique", "original", "bespoke",
    "sustainable", "upcycled", "eco",
    "stickers", "patches", "pins",
    "jewelry", "jewellery", "earrings", "necklace",
    "clothing", "apparel", "fashion",
]

# Strong negative signals — big brands, mass production, personal accounts
STRONG_NO_KEYWORDS = [
    "shipping worldwide", "worldwide shipping",  # common big brand phrase
    "fast fashion", "dropship", "wholesale",
    "free shipping on orders over",
    "ambassador", "brand rep", "affiliate link",
    "use code", "discount code", "promo code",
    "influencer", "content creator", "youtuber", "tiktok creator",
    "photographer", "photography", "photo shoot",
    # Musical artists and performers (NOT vendors)
    "dj", "dj ", "dj/", "producer", "music producer", "singer", "music", "song", "booking",
    "nightclub", "club promoter", "promoter",
    # Services not products
    "tattoo", "tattoo artist", "tattoo shop",
    "nail tech", "hair stylist", "barber",
    "speaker", "motivational speaker", "spiritual leader", "soul activator", "life coach", "healer",
    "yoga", "yoga teacher", "yoga instructor",
    "realtor", "real estate",
    "fitness", "personal trainer", "gym",
    "lawyer", "attorney", "legal",
    "doctor", "dentist", "therapist",
    "mom of", "dad of", "dog mom", "cat mom",
    "engineer", "developer", "software",
]

# Known big brand domains — instant NO
BIG_BRAND_DOMAINS = [
    "iheartraves.com", "dollskill.com", "ravewonderland.com",
    "badinka.com", "spirithoods.com", "edclv.com",
    "amazon.com", "shein.com", "romwe.com", "zaful.com",
    "fashionnova.com", "prettylittlething.com", "asos.com",
    "hottopic.com", "spencersonline.com",
    "electricfamily.com", "intotheam.com",
]

# URL patterns that suggest an actual shop (positive signal)
SHOP_URL_PATTERNS = [
    "etsy.com/shop", "etsy.com/listing",
    "bigcartel.com", "storenvy.com", "gumroad.com",
    "shopify", "squarespace", "wix.com",
    "/shop", "/store", "/products", "/collections",
]

# =============================================================================
# Category Taxonomy
# =============================================================================
CATEGORIES = [
    "Festival Clothing",
    "Jewelry & Accessories",
    "Art & Prints",
    "Home Decor",
    "Toys & Sculptures",
    "Bags & Packs",
    "Body Art & Cosmetics",
    "Stickers & Patches",
    "Other Handmade",
]

# =============================================================================
# Pipeline Settings
# =============================================================================
PROGRESS_FILE = "output/pipeline_progress.json"  # For resume capability
