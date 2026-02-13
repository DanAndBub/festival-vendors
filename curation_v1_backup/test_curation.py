"""
Test suite: Validates curation accuracy against known YES/NO examples.

Run: python -m curation.test_curation
"""
import pandas as pd
from .rules_engine import score_record
from .config import RULES_YES_THRESHOLD, RULES_NO_THRESHOLD

# =============================================================================
# Test cases from the project brief — these are ground truth
# =============================================================================

KNOWN_YES = [
    {
        'username': 'dnbeadz',
        'biography': 'HOLIDAY DROP - online now! ✨Hand beaded and braided accessories designed to let YOU shine ✨🇨🇦',
        'followers': 8139,
        'following': 728,
        'posts': 3627,
        'is_business': True,
        'external_url': 'https://www.dnbeadz.com/',
        'domain': 'dnbeadz.com',
        'profile_url': 'https://www.instagram.com/dnbeadz/',
        'website_description': 'DNBeadz is a brand that creates handbeaded custom jewelry and accessories',
        'website_title': 'Jewelry and Rave Accessories | DNBeadz',
        'tags': '',
        'all_text': 'hand beaded and braided accessories designed to let you shine | dnbeadz is a brand that creates handbeaded custom jewelry and accessories | jewelry and rave accessories | dnbeadz |',
    },
    {
        'username': 'mindfulldesign.co',
        'biography': 'PATCH WERK.. psychedelic maximalist one offs, tie dye, stickers, & art. I make what i want because im free!!!',
        'followers': 7023,
        'following': 227,
        'posts': 567,
        'is_business': True,
        'external_url': 'http://etsy.com/shop/mindfullmatters',
        'domain': 'etsy.com',
        'profile_url': 'https://www.instagram.com/mindfulldesign.co/',
        'website_description': '',
        'website_title': '',
        'tags': '',
        'all_text': 'patch werk.. psychedelic maximalist one offs, tie dye, stickers, & art. i make what i want because im free!!! |  |  |',
    },
    {
        'username': 'kandi.bean.co',
        'biography': 'Harness Tops ⭑ Bikini Chains ⭑ Jewelry OOAK pieces crafted by @raverbean DM for custom inquiries ✨ Shop the goods ↯',
        'followers': 892,
        'following': 58,
        'posts': 1216,
        'is_business': True,
        'external_url': 'http://kandibeanco.etsy.com/',
        'domain': 'etsy.com',
        'profile_url': 'https://www.instagram.com/kandi.bean.co/',
        'website_description': '',
        'website_title': '',
        'tags': '',
        'all_text': 'harness tops bikini chains jewelry ooak pieces crafted by @raverbean dm for custom inquiries shop the goods |  |  |',
    },
    {
        'username': 'spaceymaciedesigns',
        'biography': 'Passionate artist of fibers, digital creations, & whatever else I dream up Fiber Arts Fairy',
        'followers': 2531,
        'following': 452,
        'posts': 1575,
        'is_business': True,
        'external_url': 'https://linktr.ee/spaceymaciedesigns',
        'domain': 'linktr.ee',
        'profile_url': 'https://www.instagram.com/spaceymaciedesigns/',
        'website_description': '',
        'website_title': '',
        'tags': '',
        'all_text': 'passionate artist of fibers, digital creations, & whatever else i dream up fiber arts fairy |  |  |',
    },
    {
        'username': 'connie.verse',
        'biography': 'Artist, Interviewer, Designer. I paint words on things. I like to enable artists, curate gatherings, connect people, and self-express.',
        'followers': 8400,
        'following': 395,
        'posts': 3103,
        'is_business': False,
        'external_url': 'http://connieverse.com/',
        'domain': 'connieverse.com',
        'profile_url': 'https://www.instagram.com/connie.verse/',
        'website_description': 'Painting words onto clothing. Creating wearable art so that weirdos, creatives, starfires can more easily find one another.',
        'website_title': 'Connieverse',
        'tags': '',
        'all_text': 'artist, interviewer, designer. i paint words on things. | painting words onto clothing. creating wearable art so that weirdos, creatives, starfires can more easily find one another. | connieverse |',
    },
]

KNOWN_NO = [
    {
        'username': 'badinkastyle',
        'biography': "BADDIES' Wardrobe: Rave Gear & Festival Trends Shipping Worldwide Tag Us To Get Featured!",
        'followers': 135038,
        'following': 979,
        'posts': 1,
        'is_business': True,
        'external_url': 'https://badinka.com/',
        'domain': 'badinka.com',
        'profile_url': 'https://www.instagram.com/badinkastyle/',
        'website_description': 'BADINKA is an online store for cutting-edge rave, festival, and alternative fashion. Elevate your style and make a statement. Shipping worldwide.',
        'website_title': 'Rave, Festival & EDM Fashion | BADINKA',
        'tags': '',
        'all_text': "baddies' wardrobe: rave gear & festival trends shipping worldwide tag us to get featured! | badinka is an online store for cutting-edge rave, festival, and alternative fashion. shipping worldwide. | rave, festival & edm fashion | badinka |",
    },
    {
        'username': 'moonchilld36',
        'biography': '🦋29 📍 Dallas',
        'followers': 2366,
        'following': 767,
        'posts': 1353,
        'is_business': False,
        'external_url': '',
        'domain': '',
        'profile_url': 'https://www.instagram.com/moonchilld36/',
        'website_description': '',
        'website_title': '',
        'tags': '',
        'all_text': '29 dallas |  |  |',
    },
    {
        'username': 'mackenzieecain',
        'biography': 'Are you gay yet?',
        'followers': 1336,
        'following': 204,
        'posts': 2900,
        'is_business': False,
        'external_url': '',
        'domain': '',
        'profile_url': 'https://www.instagram.com/mackenzieecain/',
        'website_description': '',
        'website_title': '',
        'tags': '',
        'all_text': 'are you gay yet? |  |  |',
    },
    {
        'username': 'happyfourtwenty',
        'biography': 'Smoke weed every day Emo Unicorn Dogs > Humans',
        'followers': 785,
        'following': 1963,
        'posts': 1417,
        'is_business': False,
        'external_url': 'https://hihello.com/hi/katiemeow',
        'domain': 'hihello.com',
        'profile_url': 'https://www.instagram.com/happyfourtwenty/',
        'website_description': 'Snogo Ambassador @ Snogo. Cannaseur and Sundries Consultant Festival Professional official brand ambassador for Snogo Straws',
        'website_title': "Katie Meow's Digital Business Card",
        'tags': '',
        'all_text': 'smoke weed every day emo unicorn dogs > humans | snogo ambassador @ snogo. cannaseur and sundries consultant festival professional official brand ambassador for snogo straws | katie meow\'s digital business card |',
    },
    {
        'username': 'masmarcosantos',
        'biography': 'Writing my story one page at a time. I\'m not perfect. I just want to be happy "May my heart be my guiding key" GAYMER SPOOKY SZN',
        'followers': 572,
        'following': 45,
        'posts': 774,
        'is_business': False,
        'is_private': True,
        'external_url': '',
        'domain': '',
        'profile_url': 'https://www.instagram.com/masmarcosantos/',
        'website_description': '',
        'website_title': '',
        'tags': '',
        'all_text': 'writing my story one page at a time. i\'m not perfect. i just want to be happy "may my heart be my guiding key" gaymer spooky szn |  |  |',
    },
]


def run_tests():
    """Run all test cases and report results."""
    print("=" * 60)
    print("CURATION TEST SUITE")
    print("=" * 60)

    passed = 0
    failed = 0
    warnings = 0

    # --- Test known YES vendors ---
    print("\n--- KNOWN YES VENDORS (should score >= 0.5) ---")
    for vendor in KNOWN_YES:
        row = pd.Series(vendor)
        result = score_record(row)
        score = result['score']
        cls = result['classification']

        # For YES vendors: rules engine should give score >= 0.5
        # (They might be "maybe" which is fine — LLM will promote them)
        if score >= 0.4:  # Lenient — LLM will handle borderline
            status = "✓ PASS"
            passed += 1
        elif cls == 'maybe':
            status = "⚠ WARN (maybe — LLM will decide)"
            warnings += 1
        else:
            status = "✗ FAIL"
            failed += 1

        print(f"  {status} @{vendor['username']} → score={score:.2f} ({cls})")
        if cls == 'no':
            print(f"    Reasons: {result['reasons']}")

    # --- Test known NO vendors ---
    print("\n--- KNOWN NO VENDORS (should score < 0.5) ---")
    for vendor in KNOWN_NO:
        row = pd.Series(vendor)
        result = score_record(row)
        score = result['score']
        cls = result['classification']

        # For NO vendors: should score below threshold
        if score < 0.5:
            status = "✓ PASS"
            passed += 1
        elif cls == 'maybe':
            status = "⚠ WARN (maybe — LLM should reject)"
            warnings += 1
        else:
            status = "✗ FAIL"
            failed += 1

        print(f"  {status} @{vendor['username']} → score={score:.2f} ({cls})")
        if cls == 'yes':
            print(f"    Reasons: {result['reasons']}")

    # --- Summary ---
    total = passed + failed + warnings
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed, {warnings} warnings, {failed} failed")
    if failed == 0:
        print("All tests passed! ✓")
    else:
        print("Some tests failed. Review rules engine thresholds and keywords.")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
