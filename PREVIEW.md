# Preview Website Locally

## Option 1: Python HTTP Server (Recommended)
```bash
cd ~/.openclaw/workspace/festival-vendors/website
python3 -m http.server 8000
```

Then open: http://localhost:8000

## Option 2: Direct File Access
Simply open `website/index.html` in your browser (Chrome/Firefox/Safari).

**Note:** Some browsers block loading JSON files from `file://` protocol. If search doesn't work, use Option 1.

## What You'll See
- 526 curated festival vendors
- Search bar (real-time filtering)
- Category filters (9 categories)
- Dark theme with gradient accents
- Mobile-responsive design
- Links to Instagram + external shops

## Test Cases
Try searching for:
- "handmade" → Should show many results
- "crochet" → granny_gab and similar
- "art" → Art & Prints category
- "jewelry" → Jewelry & Accessories

Try filtering by:
- Festival Clothing (241 vendors)
- Jewelry & Accessories (95 vendors)
- Art & Prints (71 vendors)

## Mobile Testing
Resize browser window to mobile width (375px) — layout should remain clean and functional.

---

**Ready for deployment once Dan sets up VPS!**
