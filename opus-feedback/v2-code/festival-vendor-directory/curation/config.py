"""
Configuration v2 for the festival vendor curation pipeline.
Major revision based on audit of 1,965 real records.

KEY CHANGES FROM V1:
1. Rules engine NO LONGER auto-approves. Max classification = REVIEW.
   Every potential YES goes through LLM for aesthetic/intent validation.
2. Shop URL is a hard requirement for final YES.
3. Keywords reorganized: "festival fashion" alone is not enough.
4. Non-shop URL domains (YouTube, Venmo, tickets) are penalized.
5. LLM prompt completely rewritten with concrete examples.
6. Post-LLM validation gate added.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# DeepSeek API
# =============================================================================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
LLM_BATCH_SIZE = 5
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 5
LLM_TIMEOUT = 60

# =============================================================================
# Rules Engine Thresholds — V2 PHILOSOPHY
# =============================================================================
# Rules ONLY reject. Everything else goes to LLM.
# Stage 1 (Rules): Reject obvious NOs (personal accounts, big brands, no data)
# Stage 2 (LLM):   Score everything that survived Stage 1
# Stage 3 (Gate):   Hard requirements (shop URL, etc.)

MIN_FOLLOWERS = 200
MAX_FOLLOWERS = 500_000
BIG_BRAND_FOLLOWER_THRESHOLD = 80_000

# Rules engine: only has NO vs REVIEW
RULES_NO_THRESHOLD = 0.30  # Below this = definite NO
# Everything >= 0.30 goes to LLM. NO auto-YES.

# LLM must score >= this for YES
LLM_YES_THRESHOLD = 0.70

# =============================================================================
# HARD REQUIREMENTS for final YES (post-LLM gate)
# =============================================================================
REQUIRE_SHOP_URL = True
REQUIRE_MIN_FOLLOWERS = 200

# =============================================================================
# URL Classification
# =============================================================================
SHOP_DOMAINS = [
    "etsy.com", "bigcartel.com", "storenvy.com", "gumroad.com",
    "shopify.com", "squarespace.com", "wix.com",
    "depop.com", "poshmark.com", "mercari.com",
    "redbubble.com", "society6.com", "threadless.com",
    "ko-fi.com",
]

SHOP_URL_PATTERNS = [
    "/shop", "/store", "/products", "/collections",
    "/listing", "/items", "/merch", "/order",
    "etsy.com/shop/", "bigcartel.com",
]

LINK_AGGREGATOR_DOMAINS = [
    "linktr.ee", "linkin.bio", "linkr.bio", "bio.fm",
    "allmylinks.com", "beacons.ai", "lnk.bio", "tap.bio",
    "hoo.be", "snipfeed.co", "carrd.co", "solo.to",
]

NON_SHOP_DOMAINS = [
    "universe.com", "eventbrite.com", "dice.fm", "ticketmaster.com",
    "seetickets.com", "axs.com", "stubhub.com", "ra.co",
    "youtube.com", "m.youtube.com", "tiktok.com", "twitter.com", "x.com",
    "facebook.com", "m.facebook.com", "threads.net", "tumblr.com",
    "soundcloud.com", "on.soundcloud.com", "spotify.com", "open.spotify.com",
    "bandcamp.com",
    "venmo.com", "cash.app", "paypal.me", "paypal.com",
    "hihello.com", "blinq.me",
    "change.org", "gofundme.com", "patreon.com",
]

# =============================================================================
# Keyword Lists — V2
# =============================================================================

# PRODUCT keywords — they MAKE or SELL tangible products
PRODUCT_KEYWORDS = [
    "handmade", "hand made", "hand-made", "handcrafted", "hand crafted",
    "hand sewn", "hand-sewn", "hand beaded", "hand-beaded",
    "hand painted", "hand-painted",
    "made to order", "custom order", "custom made", "made by me",
    "sewn by", "crafted by", "created by",
    "i make", "i create", "i sew", "i crochet", "i knit",
    "sewing", "crochet", "knitting", "macrame",
    "beadwork", "beading", "embroidery", "weaving",
    "woodwork", "woodworking", "metalwork", "leatherwork", "leather craft",
    "resin art", "epoxy art", "polymer clay", "ceramics", "pottery",
    "fiber art", "textile art",
    "one of a kind", "ooak", "one-of-a-kind", "1/1",
    "small batch", "limited run", "limited edition",
    "wearable art", "functional art",
    "shop now", "new drop", "restocked", "available now",
    "dm for orders", "dm for custom", "dm for pricing",
    "commissions open", "customs open", "taking orders",
    "shop link in bio",
]

# AESTHETIC keywords — the trippy/festival vibe
AESTHETIC_KEYWORDS = [
    "psychedelic", "trippy", "tie dye", "tie-dye", "tiedye",
    "neon", "uv reactive", "blacklight", "glow in the dark",
    "sacred geometry", "fractal", "visionary art",
    "mushroom", "shroom",
    "bohemian", "boho",
    "cosmic", "celestial", "astral",
    "holographic", "iridescent", "prismatic",
    "kaleidoscope", "rainbow",
    "flow art", "flow toys",
    "plur", "kandi",
    "rave wear", "ravewear", "festival wear",
    "festival fashion", "festival clothing", "festival flare",
]

# NEGATIVE keywords — NOT a vendor
NEGATIVE_KEYWORDS = [
    "photographer", "photography", "photo shoot",
    "tattoo artist", "tattoo shop", "tattoo studio",
    "nail tech", "nail artist", "hair stylist", "barber",
    "dj ", "dj/", "dj.", "deejay",
    "music producer", "beatmaker",
    "promoter", "club promoter", "event promoter",
    "yoga instructor", "yoga teacher",
    "personal trainer", "fitness coach",
    "realtor", "real estate",
    "lawyer", "attorney",
    "doctor", "dentist", "therapist", "counselor",
    "influencer", "content creator",
    "brand ambassador", "ambassador for",
    "affiliate", "use my code", "use code", "discount code", "promo code",
    "vibe curator",
    "youtuber", "tiktok creator", "streamer",
    "mom of", "dad of", "dog mom", "cat mom", "fur mom",
    "mom life", "dad life",
    "just a girl", "just living",
    "wanderlust", "travel blogger",
    "foodie", "food lover",
    "shipping worldwide", "worldwide shipping", "global shipping",
    "fast fashion", "wholesale", "dropship", "drop ship",
    "tag us to get featured", "tag to be featured",
    "as seen on", "as featured in",
    "event organizer", "event planner", "event production",
    "festival organizer", "festival producer",
    "nightclub", "night club", "club night",
    "haute couture", "high fashion", "luxury fashion", "luxury brand",
]

# Personal account signals — NOT vendors
PERSONAL_ACCOUNT_SIGNALS = [
    "part-time raver", "full-time raver", "raver girl", "rave bae",
    "rave fam", "rave family",
    "festival goer", "festival lover", "festival junkie",
    "edm lover", "edm addict", "house head",
    "music lover", "concert lover",
    "living my best life", "good vibes only",
    "adventure", "adventurer", "wanderer",
    "insomniac gc", "ground control",
]

BIG_BRAND_DOMAINS = [
    "iheartraves.com", "dollskill.com", "ravewonderland.com",
    "badinka.com", "spirithoods.com", "edclv.com",
    "amazon.com", "shein.com", "romwe.com", "zaful.com",
    "fashionnova.com", "prettylittlething.com", "asos.com",
    "hottopic.com", "spencersonline.com",
    "electricfamily.com", "intotheam.com",
    "ravewithmi.com", "littleblackdiamond.com",
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
PROGRESS_FILE = "output/pipeline_progress_v2.json"
