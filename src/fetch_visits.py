"""
Fetch visit data from Software Heritage API for sampled origins.

For each sampled project, retrieves visit history to determine:
  - First visit date (proxy for project creation/discovery)
  - Last visit date (proxy for last known activity)
  - Total number of visits/snapshots

Handles SWH API rate limiting and network errors with automatic retries.
Supports resuming — skips already-fetched origins on restart.

Usage:
    python src/fetch_visits.py [--token YOUR_SWH_TOKEN]

    Optional: get an API token from https://archive.softwareheritage.org/
    to increase rate limits. Pass it with --token or set env var SWH_API_TOKEN.

Output:
    data/visit_data.csv
"""

import requests
from requests.exceptions import ConnectionError, Timeout, ChunkedEncodingError
import pandas as pd
import time
import os
import argparse
from tqdm import tqdm

INPUT_FILE = "data/sampled_origins.csv"
OUTPUT_FILE = "data/visit_data.csv"
RATE_LIMIT_PAUSE_UNAUTH = 3.5  # seconds between requests (unauthenticated)
RATE_LIMIT_PAUSE_AUTH = 1.0    # seconds between requests (authenticated)
MAX_RETRIES = 5
REQUEST_TIMEOUT = 30  # seconds


def fetch_visits_for_origin(visits_url, session):
    """Fetch all visits for a single origin from SWH API."""
    all_visits = []
    url = visits_url

    while url:
        # Retry loop for network errors
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = session.get(url, params={"per_page": 1000}, timeout=REQUEST_TIMEOUT)
                break  # success — exit retry loop
            except (ConnectionError, Timeout, ChunkedEncodingError) as e:
                if attempt == MAX_RETRIES:
                    print(f"\n  Failed after {MAX_RETRIES} retries: {type(e).__name__}")
                    return None, -1
                wait = 10 * attempt  # backoff: 10s, 20s, 30s...
                print(f"\n  Connection error (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
                time.sleep(wait)

        if response.status_code == 429:
            # Rate limited — wait and retry
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"\n  Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after + 1)
            continue

        if response.status_code != 200:
            return None, response.status_code

        visits = response.json()
        all_visits.extend(visits)

        # Check for pagination
        url = None
        link_header = response.headers.get("Link", "")
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break

    return all_visits, 200


def parse_visit_data(origin_url, visits):
    """Extract key metrics from visit list."""
    if not visits:
        return {
            "url": origin_url,
            "num_visits": 0,
            "first_visit_date": None,
            "last_visit_date": None,
            "num_snapshots": 0,
            "visit_statuses": "",
            "has_full_visit": False,
        }

    dates = []
    statuses = []
    snapshot_count = 0

    for v in visits:
        if v.get("date"):
            dates.append(v["date"])
        if v.get("status"):
            statuses.append(v["status"])
        if v.get("snapshot"):
            snapshot_count += 1

    dates_sorted = sorted(dates)

    return {
        "url": origin_url,
        "num_visits": len(visits),
        "first_visit_date": dates_sorted[0] if dates_sorted else None,
        "last_visit_date": dates_sorted[-1] if dates_sorted else None,
        "num_snapshots": snapshot_count,
        "visit_statuses": ",".join(set(statuses)),
        "has_full_visit": "full" in statuses,
    }


def load_existing_progress(output_file):
    """Load already-fetched URLs to support resuming."""
    if os.path.isfile(output_file):
        existing = pd.read_csv(output_file)
        return set(existing["url"].tolist())
    return set()


def main():
    parser = argparse.ArgumentParser(description="Fetch SWH visit data")
    parser.add_argument("--token", type=str, default=None,
                        help="SWH API token (or set SWH_API_TOKEN env var)")
    args = parser.parse_args()

    token = args.token or os.environ.get("SWH_API_TOKEN")

    # Load sampled origins
    if not os.path.isfile(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run sample_origins.py first.")
        return

    sampled = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(sampled):,} sampled origins from {INPUT_FILE}")

    # Set up session with optional auth
    session = requests.Session()
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
        rate_pause = RATE_LIMIT_PAUSE_AUTH
        print("Using authenticated requests (higher rate limit, ~1s between requests)")
    else:
        rate_pause = RATE_LIMIT_PAUSE_UNAUTH
        print("Using unauthenticated requests (rate limit ~1200 req/hr)")
        print("Tip: Get a token at https://archive.softwareheritage.org/ for faster collection")

    # Load progress for resuming
    done_urls = load_existing_progress(OUTPUT_FILE)
    if done_urls:
        print(f"Resuming: {len(done_urls):,} origins already fetched, skipping them.")

    # Filter to remaining work
    remaining = sampled[~sampled["url"].isin(done_urls)]
    print(f"Origins to fetch: {len(remaining):,}")

    if len(remaining) == 0:
        print("All origins already fetched!")
        return

    # Fetch visits
    results = []
    errors = 0
    write_header = not os.path.isfile(OUTPUT_FILE)

    for _, row in tqdm(remaining.iterrows(), total=len(remaining), desc="Fetching visits"):
        visits_url = row["origin_visits_url"]
        origin_url = row["url"]

        visits, status_code = fetch_visits_for_origin(visits_url, session)

        if visits is not None:
            record = parse_visit_data(origin_url, visits)
            results.append(record)
        else:
            results.append({
                "url": origin_url,
                "num_visits": 0,
                "first_visit_date": None,
                "last_visit_date": None,
                "num_snapshots": 0,
                "visit_statuses": f"error_{status_code}",
                "has_full_visit": False,
            })
            errors += 1

        # Write in batches of 50 to avoid losing progress
        if len(results) >= 50:
            batch_df = pd.DataFrame(results)
            batch_df.to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)
            write_header = False
            results = []

        # Rate limiting
        time.sleep(rate_pause)

    # Write remaining results
    if results:
        batch_df = pd.DataFrame(results)
        batch_df.to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)

    # Final summary
    if os.path.isfile(OUTPUT_FILE):
        final = pd.read_csv(OUTPUT_FILE)
        print(f"\nDone! Total records in {OUTPUT_FILE}: {len(final):,}")
        print(f"Errors this run: {errors}")
        print(f"Records with snapshots: {final['num_snapshots'].gt(0).sum():,}")
    else:
        print(f"\nCompleted with {errors} errors.")


if __name__ == "__main__":
    main()
