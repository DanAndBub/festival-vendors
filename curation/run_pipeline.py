"""
Pipeline Orchestrator: Runs all curation steps in sequence.

Usage:
    python -m curation.run_pipeline --input scraped.csv --output output/

Options:
    --input PATH       Path to scraped Instagram CSV
    --output DIR       Output directory (default: output/)
    --incremental      Skip already-processed usernames
    --full             Force re-process everything
    --skip-llm         Skip LLM curation (rules only — for testing)
    --skip-categories  Skip category tagging
"""
import argparse
import json
import os
import sys
import pandas as pd
from datetime import datetime

from .data_loader import load_data
from .rules_engine import run_rules_engine
from .llm_curator import run_llm_curation
from .category_tagger import run_category_tagger
from .config import FINAL_INCLUSION_THRESHOLD


def run_pipeline(
    input_csv: str,
    output_dir: str = "output",
    incremental: bool = False,
    skip_llm: bool = False,
    skip_categories: bool = False,
):
    """Run the full curation pipeline."""
    os.makedirs(output_dir, exist_ok=True)

    start_time = datetime.now()
    print(f"{'='*60}")
    print(f"Festival Vendor Curation Pipeline")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Input: {input_csv}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}\n")

    # --- Step 1: Load Data ---
    print("STEP 1/4: Loading and normalizing data...")
    df = load_data(input_csv)
    print(f"  → {len(df)} records loaded\n")

    # --- Handle incremental mode ---
    existing_output = os.path.join(output_dir, "curated_vendors.json")
    if incremental and os.path.exists(existing_output):
        with open(existing_output, 'r') as f:
            existing = json.load(f)
        existing_usernames = {v['username'] for v in existing}
        new_count = (~df['username'].isin(existing_usernames)).sum()
        print(f"  [incremental] {len(existing_usernames)} already processed, "
              f"{new_count} new records")
        if new_count == 0:
            print("  [incremental] No new records to process. Done!")
            return
        # Only process new records through the pipeline
        df_new = df[~df['username'].isin(existing_usernames)].copy()
        df_existing = df[df['username'].isin(existing_usernames)].copy()
    else:
        df_new = df
        df_existing = pd.DataFrame()

    # --- Step 2: Rules Engine ---
    print("STEP 2/4: Running rules engine...")
    df_new = run_rules_engine(df_new)

    # --- Step 3: LLM Curation ---
    if skip_llm:
        print("\nSTEP 3/4: SKIPPED (--skip-llm flag)")
        df_new['llm_score'] = None
        df_new['llm_reason'] = ''
        df_new['final_score'] = df_new['rules_score']
        df_new['final_classification'] = df_new['rules_classification']
        # Promote "maybe" to "no" when skipping LLM
        df_new.loc[df_new['final_classification'] == 'maybe', 'final_classification'] = 'no'
    else:
        print("\nSTEP 3/4: Running LLM curation on ambiguous records...")
        df_new = run_llm_curation(df_new)

    # --- Step 4: Category Tagging ---
    if skip_categories:
        print("\nSTEP 4/4: SKIPPED (--skip-categories flag)")
        df_new['categories'] = '["Other Handmade"]'
    else:
        print("\nSTEP 4/4: Assigning categories to curated vendors...")
        df_new = run_category_tagger(df_new)

    # --- Merge incremental results ---
    # (for incremental, we'd need to merge, but for now just use df_new)
    df_final = df_new

    # --- Save Outputs ---
    print(f"\n{'='*60}")
    print("Saving outputs...")

    # 1. Full CSV with all scores (for debugging/review)
    full_csv_path = os.path.join(output_dir, "full_scored.csv")
    df_final.to_csv(full_csv_path, index=False)
    print(f"  Full scored CSV: {full_csv_path}")

    # 2. Curated vendors JSON (for website)
    curated = df_final[df_final['final_classification'] == 'yes'].copy()
    curated = curated.sort_values('final_score', ascending=False)

    vendors_list = []
    for _, row in curated.iterrows():
        categories = ['Other Handmade']
        if row.get('categories'):
            try:
                categories = json.loads(row['categories'])
            except (json.JSONDecodeError, TypeError):
                pass

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
            'categories': categories,
            'llm_reason': row.get('llm_reason', ''),
        })

    json_path = os.path.join(output_dir, "curated_vendors.json")
    with open(json_path, 'w') as f:
        json.dump(vendors_list, f, indent=2)
    print(f"  Curated vendors JSON: {json_path} ({len(vendors_list)} vendors)")

    # 3. Curated vendors CSV (for human review)
    curated_csv_path = os.path.join(output_dir, "curated_vendors.csv")
    review_cols = [
        'username', 'biography', 'followers', 'external_url',
        'final_score', 'categories', 'rules_reasons', 'llm_reason'
    ]
    review_cols = [c for c in review_cols if c in curated.columns]
    curated[review_cols].to_csv(curated_csv_path, index=False)
    print(f"  Curated vendors CSV: {curated_csv_path}")

    # --- Summary ---
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"Pipeline complete!")
    print(f"  Total records processed: {len(df_final)}")
    print(f"  Curated vendors: {len(vendors_list)}")
    print(f"  Rejection rate: {(1 - len(vendors_list)/len(df_final))*100:.1f}%")
    print(f"  Time elapsed: {elapsed:.1f}s")
    print(f"{'='*60}")

    return vendors_list


def main():
    parser = argparse.ArgumentParser(description="Festival Vendor Curation Pipeline")
    parser.add_argument("--input", required=True, help="Path to scraped Instagram CSV")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--incremental", action="store_true",
                        help="Only process new records")
    parser.add_argument("--full", action="store_true",
                        help="Force re-process everything")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip LLM curation (rules only)")
    parser.add_argument("--skip-categories", action="store_true",
                        help="Skip category tagging")
    args = parser.parse_args()

    if args.full:
        # Clear progress file for full rerun
        from .config import PROGRESS_FILE
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print("[pipeline] Cleared progress file for full rerun")

    run_pipeline(
        input_csv=args.input,
        output_dir=args.output,
        incremental=args.incremental and not args.full,
        skip_llm=args.skip_llm,
        skip_categories=args.skip_categories,
    )


if __name__ == "__main__":
    main()
