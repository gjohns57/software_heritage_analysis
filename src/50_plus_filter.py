"""
Filter analysis_dataset.csv to only languages with 50+ projects.

Removes the "Other" catch-all category and any language with fewer than
50 projects — these lack statistical power for survival analysis.

Usage:
    python src/50_plus_filter.py

Input:
    data/analysis_dataset.csv (12,310 projects, 100 languages)

Output:
    data/analysis_50plus.csv (languages with 50+ projects each)
"""

import pandas as pd

INPUT_FILE = "data/analysis_dataset.csv"
OUTPUT_FILE = "data/analysis_50plus.csv"


def main():
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df):,} projects across {df['primary_language'].nunique()} languages")

    # Count projects per language
    lang_counts = df["primary_language"].value_counts()

    # Keep languages with 50+ projects, exclude "Other"
    keep_languages = lang_counts[(lang_counts >= 50) & (lang_counts.index != "Other")].index.tolist()

    filtered = df[df["primary_language"].isin(keep_languages)].copy()

    removed_projects = len(df) - len(filtered)
    removed_languages = df["primary_language"].nunique() - len(keep_languages)

    print(f"\nKept {len(keep_languages)} languages with 50+ projects")
    print(f"Removed {removed_projects:,} projects ({removed_languages} languages with < 50 projects + 'Other')")

    # Save
    filtered.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(filtered):,} projects to {OUTPUT_FILE}")

    # Summary
    print(f"\n{'Language':25s} {'Projects':>10s} {'Pct':>8s}")
    print("-" * 45)
    for lang in keep_languages:
        count = lang_counts[lang]
        pct = 100 * count / len(filtered)
        print(f"{lang:25s} {count:10,} {pct:7.1f}%")
    print("-" * 45)
    print(f"{'TOTAL':25s} {len(filtered):10,} {'100.0%':>8s}")


if __name__ == "__main__":
    main()
