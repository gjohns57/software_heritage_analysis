"""
Detect primary programming language using GitHub's GraphQL API.

This is MUCH faster than the REST API — queries 50 repos per request,
so 20,000 repos = ~400 requests instead of 20,000.

Usage:
    python src/fetch_languages_graphql.py --github-token YOUR_GITHUB_TOKEN

Output:
    data/language_data.csv
"""

import requests
from requests.exceptions import ConnectionError, Timeout, ChunkedEncodingError
import pandas as pd
import time
import os
import argparse
from tqdm import tqdm

INPUT_FILE = "data/sampled_origins.csv"
OUTPUT_FILE = "data/language_data.csv"
GRAPHQL_URL = "https://api.github.com/graphql"
BATCH_SIZE = 50  # repos per GraphQL query
MAX_RETRIES = 5
REQUEST_TIMEOUT = 60


def build_graphql_query(repos):
    """Build a batched GraphQL query for multiple repos."""
    parts = []
    for i, (owner, name) in enumerate(repos):
        # GraphQL aliases must be alphanumeric, use r0, r1, r2...
        parts.append(f"""
        r{i}: repository(owner: "{owner}", name: "{name}") {{
            nameWithOwner
            primaryLanguage {{
                name
            }}
            languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
                edges {{
                    node {{
                        name
                    }}
                    size
                }}
                totalSize
            }}
        }}
        """)

    return "query {\n" + "\n".join(parts) + "\n}"


def safe_graphql_request(session, query):
    """Make a GraphQL request with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(
                GRAPHQL_URL,
                json={"query": query},
                timeout=REQUEST_TIMEOUT,
            )
            return response
        except (ConnectionError, Timeout, ChunkedEncodingError) as e:
            if attempt == MAX_RETRIES:
                print(f"\n  Failed after {MAX_RETRIES} retries: {type(e).__name__}")
                return None
            wait = 10 * attempt
            print(f"\n  Connection error (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)
    return None


def parse_batch_response(data, repo_list):
    """Parse GraphQL response into records."""
    results = []
    for i, (owner, name) in enumerate(repo_list):
        key = f"r{i}"
        repo_data = data.get(key)
        full_name = f"{owner}/{name}"

        if repo_data is None:
            # Repo not found / private / deleted
            results.append({
                "url": f"https://github.com/{full_name}",
                "repo_full_name": full_name,
                "primary_language": None,
                "primary_language_ratio": 0,
                "github_languages": "",
                "language_source": "unknown",
                "github_status": "not_found",
            })
            continue

        # Primary language
        primary_lang = None
        if repo_data.get("primaryLanguage"):
            primary_lang = repo_data["primaryLanguage"]["name"]

        # All languages with byte counts
        lang_dict = {}
        total_size = repo_data.get("languages", {}).get("totalSize", 0)
        for edge in repo_data.get("languages", {}).get("edges", []):
            lang_name = edge["node"]["name"]
            lang_size = edge["size"]
            lang_dict[lang_name] = lang_size

        # Calculate primary language ratio
        lang_ratio = 0
        if primary_lang and total_size > 0 and primary_lang in lang_dict:
            lang_ratio = lang_dict[primary_lang] / total_size

        results.append({
            "url": f"https://github.com/{full_name}",
            "repo_full_name": full_name,
            "primary_language": primary_lang,
            "primary_language_ratio": round(lang_ratio, 4),
            "github_languages": str(lang_dict) if lang_dict else "",
            "language_source": "github" if primary_lang else "unknown",
            "github_status": "ok" if primary_lang else ("no_languages" if repo_data else "not_found"),
        })

    return results


def load_existing_progress(output_file):
    """Load already-fetched URLs to support resuming."""
    if os.path.isfile(output_file):
        existing = pd.read_csv(output_file)
        return set(existing["url"].tolist())
    return set()


def main():
    parser = argparse.ArgumentParser(description="Fetch language data via GitHub GraphQL API")
    parser.add_argument("--github-token", type=str, default=None,
                        help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    args = parser.parse_args()

    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")

    if not github_token:
        print("Error: GitHub token is required for GraphQL API.")
        print("Create one at: https://github.com/settings/tokens")
        return

    # Load sampled origins
    if not os.path.isfile(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run sample_origins.py first.")
        return

    sampled = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(sampled):,} sampled origins from {INPUT_FILE}")

    # Set up session
    session = requests.Session()
    session.headers["Authorization"] = f"bearer {github_token}"
    session.headers["Content-Type"] = "application/json"

    # Check rate limit
    check_query = "query { rateLimit { remaining resetAt limit } }"
    resp = safe_graphql_request(session, check_query)
    if resp and resp.status_code == 200:
        rl = resp.json().get("data", {}).get("rateLimit", {})
        print(f"GraphQL rate limit: {rl.get('remaining', '?')}/{rl.get('limit', '?')} points, "
              f"resets at {rl.get('resetAt', '?')}")
    else:
        print("Warning: Could not check rate limit")

    # Load progress for resuming
    done_urls = load_existing_progress(OUTPUT_FILE)
    if done_urls:
        print(f"Resuming: {len(done_urls):,} origins already fetched, skipping them.")

    remaining = sampled[~sampled["url"].isin(done_urls)]
    print(f"Origins to fetch: {len(remaining):,}")

    if len(remaining) == 0:
        print("All origins already fetched!")
        return

    # Parse owner/name pairs
    repo_pairs = []
    for _, row in remaining.iterrows():
        full_name = row.get("repo_full_name", row["url"].replace("https://github.com/", ""))
        parts = full_name.strip("/").split("/")
        if len(parts) >= 2:
            repo_pairs.append((parts[0], parts[1]))
        else:
            repo_pairs.append((full_name, ""))

    # Process in batches
    write_header = not os.path.isfile(OUTPUT_FILE)
    total_batches = (len(repo_pairs) + BATCH_SIZE - 1) // BATCH_SIZE
    all_results = []
    errors = 0

    for batch_idx in tqdm(range(0, len(repo_pairs), BATCH_SIZE), total=total_batches, desc="Fetching languages"):
        batch = repo_pairs[batch_idx:batch_idx + BATCH_SIZE]

        query = build_graphql_query(batch)
        response = safe_graphql_request(session, query)

        if response is None:
            # Connection failed — record errors for this batch
            for owner, name in batch:
                all_results.append({
                    "url": f"https://github.com/{owner}/{name}",
                    "repo_full_name": f"{owner}/{name}",
                    "primary_language": None,
                    "primary_language_ratio": 0,
                    "github_languages": "",
                    "language_source": "unknown",
                    "github_status": "connection_error",
                })
            errors += len(batch)
            time.sleep(10)
            continue

        if response.status_code != 200:
            # Check for rate limiting
            if response.status_code == 403 or response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait = int(retry_after) + 5
                else:
                    wait = 65
                print(f"\n  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                # Retry this batch
                response = safe_graphql_request(session, query)
                if response is None or response.status_code != 200:
                    errors += len(batch)
                    continue

        resp_json = response.json()

        # Check for GraphQL-level rate limit / errors
        if "errors" in resp_json and not resp_json.get("data"):
            error_msg = resp_json["errors"][0].get("message", "")
            if "rate limit" in error_msg.lower():
                print(f"\n  GraphQL rate limit hit. Waiting 65s...")
                time.sleep(65)
                response = safe_graphql_request(session, query)
                if response and response.status_code == 200:
                    resp_json = response.json()
                else:
                    errors += len(batch)
                    continue

        data = resp_json.get("data", {})
        batch_results = parse_batch_response(data, batch)
        all_results.extend(batch_results)

        # Write every 5 batches (250 records)
        if len(all_results) >= 250:
            batch_df = pd.DataFrame(all_results)
            batch_df.to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)
            write_header = False
            all_results = []

        # Pace requests — GraphQL costs ~1 point per node, 50 nodes = ~50 points
        # With 5000 points/hr, we can do ~100 batches/hr safely
        time.sleep(3)

    # Write remaining
    if all_results:
        batch_df = pd.DataFrame(all_results)
        batch_df.to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)

    # Summary
    if os.path.isfile(OUTPUT_FILE):
        final = pd.read_csv(OUTPUT_FILE)
        print(f"\nDone! Total records in {OUTPUT_FILE}: {len(final):,}")
        print(f"Errors: {errors}")
        detected = final["primary_language"].notna().sum()
        print(f"Language detected: {detected:,} / {len(final):,} ({100*detected/len(final):.1f}%)")
        print(f"\nLanguage distribution (top 20):")
        print(final["primary_language"].value_counts().head(20).to_string())


if __name__ == "__main__":
    main()
