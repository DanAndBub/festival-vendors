"""
Collect individual vendor JSON files into a single results file.
"""
import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"

def main():
    print("📦 Collecting individual vendor results...")
    
    results = []
    json_files = sorted(OUTPUT_DIR.glob("*.json"))
    
    # Skip summary files
    skip_files = {'non_etsy_results.json', 'non_etsy_results_v2.json', 
                  'scrape_v2_summary.json', 'test_run_final_summary.json',
                  'PHASE1_TEST_SUMMARY.json', 'etsy_scrape_raw.json'}
    
    for json_file in json_files:
        if json_file.name in skip_files:
            continue
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                results.append(data)
                print(f"  ✓ {data['username']}")
        except Exception as e:
            print(f"  ✗ {json_file.name}: {e}")
    
    # Save collected results
    output_file = OUTPUT_DIR / "non_etsy_results_v2.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Collected {len(results)} vendor results")
    print(f"💾 Saved to: {output_file}")
    
    # Create summary
    source_counts = {}
    for r in results:
        source = r.get('source', 'unknown')
        source_counts[source] = source_counts.get(source, 0) + 1
    
    print(f"\n📊 Source Breakdown:")
    for source, count in sorted(source_counts.items()):
        print(f"   {source.ljust(25)} {count:3d}")

if __name__ == "__main__":
    main()
