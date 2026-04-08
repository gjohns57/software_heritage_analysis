"""
Fetch commit counts for sampled GitHub projects using GraphQL API.

Queries the total commit count on the default branch for each project.
Batches 50 repos per request — 20K repos in ~400 requests (~25 min).

Usage:
    python src/fetch_commits.py --github-token YOUR_GITHUB_TOKEN

Output:
    data/commit_data.csv
"""

import requests
from requests.exceptions import ConnectionError, Timeout, ChunkedEncodingError
import pandas as pd
import time
import os
import argparse
from tqdm import tqdm

INPUT_FILE = "data/sampled_origins.csv"
OUTPUT_FILE = "data/commit_data.csv"
GRAPHQL_URL = "https://api.github.com/graphql"
BATCH_SIZE = 50
MAX_RETRIES = 5
REQUEST_TIMEOUT = 60


def build_query(repos):
    """Build a batched GraphQL query for commit counts."""
    parts = []
    for i, (owner, name) in enumerate(repos):
        parts.append(f"""
        r{i}: repository(owner: "{owner}", name: "{name}") {{
            nameWithOwner
            defaultBranchRef {{
                target {{
                    ... on Commit {{
                        history {{
                            totalCount
                        }}
                    }}
                }}
            }}
        }}
        """)
    return "query {\n" + "\n".join(parts) + "\n}"


def safe_request(session, query):
    """Make a GraphQL request with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return session.post(GRAPHQL_URL, json={"query": query}, timeout=REQUEST_TIMEOUT)
        except (ConnectionError, Timeout, ChunkedEncodingError) as e:
            if attempt == MAX_RETRIES:
                print(f"\n  Failed after {MAX_RETRIES} retries: {type(e).__name__}")
                return None
            wait = 10 * attempt
            print(f"\n  Connection error (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)
    return None


def parse_batch(data, repo_list):
    """Parse GraphQL response into records."""
    results = []
    for i, (owner, name) in enumerate(repo_list):
        full_name = f"{owner}/{name}"
        repo_data = data.get(f"r{i}")

        commit_count = 0
        status = "not_found"

        if repo_data:
            branch = repo_data.get("defaultBranchRef")
            if branch and branch.get("target"):
                history = branch["target"].get("history", {})
                commit_count = history.get("totalCount", 0)
                status = "ok"
            else:
                status = "no_default_branch"

        results.append({
            "url": f"https://github.com/{full_name}",
            "repo_full_name": full_name,
            "commit_count": commit_count,
            "commit_status": status,
        })
    return results


def load_existing_progress(output_file):
    if os.path.isfile(output_file):
        existing = pd.read_csv(output_file)
        return set(existing["url"].tolist())
    return set()


def main():
    parser = argparse.ArgumentParser(description="Fetch commit counts via GitHub GraphQL")
    parser.add_argument("--github-token", type=str, default=None,
                        help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    args = parser.parse_args()

    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("Error: GitHub token required. Pass --github-token or set GITHUB_TOKEN env var.")
        return

    if not os.path.isfile(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run sample_origins.py first.")
        return

    sampled = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(sampled):,} sampled origins")

    session = requests.Session()
    session.headers["Authorization"] = f"bearer {github_token}"
    session.headers["Content-Type"] = "application/json"

    # Check rate limit
    resp = safe_request(session, "query { rateLimit { remaining resetAt limit } }")
    if resp and resp.status_code == 200:
        rl = resp.json().get("data", {}).get("rateLimit", {})
        print(f"GraphQL rate limit: {rl.get('remaining', '?')}/{rl.get('limit', '?')} points, "
              f"resets at {rl.get('resetAt', '?')}")

    # Resume support
    done_urls = load_existing_progress(OUTPUT_FILE)
    if done_urls:
        print(f"Resuming: {len(done_urls):,} already fetched, skipping.")

    remaining = sampled[~sampled["url"].isin(done_urls)]
    print(f"Origins to fetch: {len(remaining):,}")

    if len(remaining) == 0:
        print("All done!")
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

    write_header = not os.path.isfile(OUTPUT_FILE)
    all_results = []
    errors = 0
    total_batches = (len(repo_pairs) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in tqdm(range(0, len(repo_pairs), BATCH_SIZE), total=total_batches, desc="Fetching commits"):
        batch = repo_pairs[batch_idx:batch_idx + BATCH_SIZE]
        query = build_query(batch)
        response = safe_request(session, query)

        if response is None:
            for owner, name in batch:
                all_results.append({
                    "url": f"https://github.com/{owner}/{name}",
                    "repo_full_name": f"{owner}/{name}",
                    "commit_count": 0,
                    "commit_status": "connection_error",
                })
            errors += len(batch)
            time.sleep(10)
            continue

        if response.status_code in (403, 429):
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) + 5 if retry_after else 65
            print(f"\n  Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            response = safe_request(session, query)
            if response is None or response.status_code != 200:
                errors += len(batch)
                continue

        resp_json = response.json()

        if "errors" in resp_json and not resp_json.get("data"):
            error_msg = resp_json["errors"][0].get("message", "")
            if "rate limit" in error_msg.lower():
                print(f"\n  GraphQL rate limit. Waiting 65s...")
                time.sleep(65)
                response = safe_request(session, query)
                if response and response.status_code == 200:
                    resp_json = response.json()
                else:
                    errors += len(batch)
                    continue

        data = resp_json.get("data", {})
        batch_results = parse_batch(data, batch)
        all_results.extend(batch_results)

        if len(all_results) >= 250:
            pd.DataFrame(all_results).to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)
            write_header = False
            all_results = []

        time.sleep(3)

    if all_results:
        pd.DataFrame(all_results).to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)

    if os.path.isfile(OUTPUT_FILE):
        final = pd.read_csv(OUTPUT_FILE)
        print(f"\nDone! Total: {len(final):,}")
        print(f"Errors: {errors}")
        print(f"\nCommit count distribution:")
        print(final["commit_count"].describe().to_string())
        for t in [10, 20, 50, 100]:
            c = (final["commit_count"] >= t).sum()
            print(f"  >= {t} commits: {c:,} ({100*c/len(final):.1f}%)")


if __name__ == "__main__":
    main()
