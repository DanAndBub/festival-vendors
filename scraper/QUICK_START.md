# Quick Start Guide

## 🚀 Run the Scraper

### Test Mode (4 vendors, one per platform)
```bash
cd /home/bumby/.openclaw/workspace/festival-vendors
python3 scraper/scrape_all.py
```

**Runtime:** ~30 seconds  
**Output:** 
- Images in `images/{vendor-slug}/`
- Metadata in `scraper/output/{vendor-slug}.json`
- Summary in `scraper/output/PHASE1_TEST_SUMMARY.json`

---

## 📊 Quick Stats

- **Total vendors:** 199
- **Automated:** 191 (96%)
- **Platforms:** Shopify (6), Etsy (45), BigCartel (9), Custom (131), Depop (8 manual)
- **Test status:** ✅ 4/4 platforms working (100% success)

---

## 📁 Output Structure

```
festival-vendors/
├── images/
│   └── {vendor-slug}/
│       ├── product_1.jpg  ← Max 800px wide, JPEG
│       ├── product_2.jpg
│       └── ...
└── scraper/
    └── output/
        ├── {vendor-slug}.json  ← Metadata
        └── PHASE1_TEST_SUMMARY.json
```

---

## 🔧 How It Works

### By Platform:

| Platform | Method | Speed | Quality |
|----------|--------|-------|---------|
| Shopify | API call | Fast ⚡ | Perfect ✅ |
| Etsy | Instagram images | Instant ⚡⚡ | Good ✅ |
| BigCartel | HTML scrape | Medium 🐢 | Good ✅ |
| Custom | HTML scrape | Medium 🐢 | Varies ⚠️ |
| Depop | Manual | N/A | N/A |

---

## ⚙️ Configuration

No configuration needed! Everything is pre-configured:

- ✅ APIFY_TOKEN already set in environment
- ✅ Vendor list at `website/vendors.json`
- ✅ Instagram images at `data/vendor_images.json`

---

## 🔍 Check Results

### View summary:
```bash
cat scraper/output/PHASE1_TEST_SUMMARY.json
```

### Check images:
```bash
ls -lh images/*/
```

### View vendor metadata:
```bash
cat scraper/output/sunnydazewithsam.json
```

---

## 📖 Full Documentation

- `README.md` - Complete technical guide
- `COMPLETION_REPORT.md` - Detailed completion report
- `QUICK_START.md` - This file

---

## 🚦 Next Steps (Phase 2)

To scale to all 191 vendors:

1. Modify `scrape_all.py` to remove test mode
2. Add rate limiting (2-3 sec delays)
3. Process in batches of 20
4. Run overnight

**Estimated time:** 10-15 minutes for full run

---

## 🐛 Troubleshooting

### No images downloaded?
- Check internet connection
- Vendor site might be down
- Try running again (might be rate limited)

### Images too small?
- BigCartel returns thumbnails sometimes
- Can enhance to extract full-size URLs

### Missing metadata?
- Check `scraper/output/` directory exists
- Script creates it automatically on first run

---

## 💡 Tips

1. **Test first:** Always run in test mode before scaling
2. **Check outputs:** Review a few images before bulk processing
3. **Rate limit:** Add delays if scraping many sites
4. **Backup:** Images and metadata are safe to re-run (overwrites)

---

**Questions?** Check `README.md` or `COMPLETION_REPORT.md`
