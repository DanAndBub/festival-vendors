"""
Pipeline Orchestrator v2.

Usage:
    python -m curation.run_pipeline --input scraped.csv --output output/
    python -m curation.run_pipeline --input scraped.csv --output output/ --skip-llm
    python -m curation.run_pipeline --input scraped.csv --output output/ --full
"""
import argparse
import json
import os
import pandas as pd
from datetime import datetime

from .data_loader import load_data
from .rules_engine import run_rules_engine
from .llm_curator import run_llm_curation
from .category_tagger import run_category_tagger


def run_pipeline(input_csv, output_dir="output", skip_llm=False, skip_categories=False):
    os.makedirs(output_dir, exist_ok=True)
    start = datetime.now()
    print(f"{'='*60}")
    print(f"Festival Vendor Curation Pipeline v2")
    print(f"Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Step 1: Load
    print("STEP 1: Loading data...")
    df = load_data(input_csv)
    print(f"  {len(df)} records\n")

    # Step 2: Rules (reject obvious NOs)
    print("STEP 2: Rules engine (filtering trash)...")
    df = run_rules_engine(df)

    # Step 3: LLM (judge everything that survived)
    if skip_llm:
        print("\nSTEP 3: SKIPPED (--skip-llm)")
        df['llm_score'] = pd.NA
        df['llm_reason'] = ''
        df['final_score'] = df['rules_score']
        # Without LLM, nothing gets approved
        df['final_classification'] = df['rules_classification'].apply(
            lambda x: 'review_pending' if x == 'review' else 'no'
        )
    else:
        print("\nSTEP 3: LLM curation...")
        df = run_llm_curation(df)

    # Step 4: Categories + Tags
    if skip_categories or skip_llm:
        print("\nSTEP 4: SKIPPED")
        if 'categories' not in df.columns:
            df['categories'] = ''
        if 'vendor_tags' not in df.columns:
            df['vendor_tags'] = ''
    else:
        print("\nSTEP 4: Category tagging...")
        df = run_category_tagger(df)

    # Save outputs
    print(f"\n{'='*60}")
    print("Saving outputs...")

    # Full CSV (debug/review)
    df.to_csv(os.path.join(output_dir, "full_scored.csv"), index=False)

    # Curated JSON (for website)
    curated = df[df['final_classification'] == 'yes'].sort_values('final_score', ascending=False)
    vendors_list = []
    for _, row in curated.iterrows():
        cats = ['Other Handmade']
        tags = []
        try: cats = json.loads(row.get('categories', '[]'))
        except: pass
        try: tags = json.loads(row.get('vendor_tags', '[]'))
        except: pass

        vendors_list.append({
            'username': row['username'],
            'biography': row.get('biography', ''),
            'followers': int(row.get('followers', 0)),
            'is_business': bool(row.get('is_business', False)),
            'external_url': row.get('external_url', ''),
            'domain': row.get('domain', ''),
            'profile_url': row.get('profile_url', ''),
            'website_title': row.get('website_title', ''),
            'website_description': row.get('website_description', ''),
            'confidence_score': float(row.get('final_score', 0)),
            'categories': cats,
            'tags': tags,
            'llm_reason': row.get('llm_reason', ''),
        })

    with open(os.path.join(output_dir, "curated_vendors.json"), 'w') as f:
        json.dump(vendors_list, f, indent=2)

    # CSV for human review
    review_cols = ['username', 'biography', 'followers', 'external_url', 'domain',
                   'rules_score', 'rules_classification', 'llm_score', 'llm_reason',
                   'sells_products', 'has_shop', 'festival_aesthetic',
                   'final_score', 'final_classification', 'categories', 'vendor_tags']
    review_cols = [c for c in review_cols if c in df.columns]
    curated[review_cols].to_csv(os.path.join(output_dir, "curated_vendors.csv"), index=False)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"Pipeline v2 complete!")
    print(f"  Records processed: {len(df)}")
    print(f"  Rules rejected: {(df['rules_classification'] == 'no').sum()}")
    print(f"  LLM reviewed: {(df['rules_classification'] == 'review').sum()}")
    print(f"  Final approved: {len(vendors_list)}")
    print(f"  Approval rate: {len(vendors_list)/len(df)*100:.1f}%")
    print(f"  Time: {elapsed:.1f}s")
    print(f"{'='*60}")
    return vendors_list


def main():
    parser = argparse.ArgumentParser(description="Festival Vendor Curation Pipeline v2")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="output")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--skip-categories", action="store_true")
    parser.add_argument("--full", action="store_true", help="Clear cache and reprocess")
    args = parser.parse_args()

    if args.full:
        from .config import PROGRESS_FILE
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print("Cleared LLM cache for full rerun")

    run_pipeline(args.input, args.output, args.skip_llm, args.skip_categories)


if __name__ == "__main__":
    main()
