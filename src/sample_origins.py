"""
Sample 20,000 GitHub-only projects from link_store.csv.

Reads the large CSV in chunks, filters to GitHub origins only,
and takes a random sample of 20,000 projects.

Usage:
    python src/sample_origins.py

Output:
    data/sampled_origins.csv  (20,000 rows with url and origin_visits_url)
"""

import pandas as pd
import os

SAMPLE_SIZE = 20_000
INPUT_FILE = "data/link_store.csv"
OUTPUT_FILE = "data/sampled_origins.csv"
CHUNK_SIZE = 500_000
RANDOM_SEED = 42


def main():
    print(f"Reading {INPUT_FILE} in chunks and filtering to GitHub origins...")

    github_chunks = []
    total_rows = 0
    github_rows = 0

    for chunk in pd.read_csv(INPUT_FILE, chunksize=CHUNK_SIZE):
        # Standardize column names (the CSV has a space: "url, origin_visits_url")
        chunk.columns = [c.strip() for c in chunk.columns]

        total_rows += len(chunk)

        # Filter to GitHub-only origins
        mask = chunk["url"].str.startswith("https://github.com/", na=False)
        github_chunk = chunk[mask]
        github_rows += len(github_chunk)

        github_chunks.append(github_chunk)

        print(f"  Processed {total_rows:,} rows, GitHub so far: {github_rows:,}")

    print(f"\nTotal rows: {total_rows:,}")
    print(f"GitHub rows: {github_rows:,}")

    # Combine all GitHub rows
    all_github = pd.concat(github_chunks, ignore_index=True)

    # Sample
    if len(all_github) < SAMPLE_SIZE:
        print(f"Warning: Only {len(all_github):,} GitHub origins found, using all.")
        sampled = all_github
    else:
        sampled = all_github.sample(n=SAMPLE_SIZE, random_state=RANDOM_SEED)

    # Extract owner/repo for convenience
    sampled = sampled.copy()
    sampled["repo_full_name"] = sampled["url"].str.replace(
        "https://github.com/", "", regex=False
    )

    # Save
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    sampled.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(sampled):,} sampled origins to {OUTPUT_FILE}")

    # Print some stats
    print(f"\nSample preview:")
    print(sampled.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
