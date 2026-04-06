"""
Detect primary programming language for sampled GitHub projects.

Two approaches:
  1. GitHub API: repos/{owner}/{repo}/languages — returns byte counts per language.
  2. SWH file extensions: From the latest snapshot, analyze file extensions
     and map them to languages (fallback, aligns with Desmazières et al. [6]).

Usage:
    python src/fetch_languages.py --github-token YOUR_GITHUB_TOKEN [--swh-token YOUR_SWH_TOKEN]

    A GitHub personal access token is required (unauthenticated = 60 req/hr,
    authenticated = 5000 req/hr). Create one at:
    https://github.com/settings/tokens (no special scopes needed, public_repo access).

    SWH token is optional but recommended for the file extension fallback.

Output:
    data/language_data.csv
"""

import requests
import pandas as pd
import time
import os
import argparse
from tqdm import tqdm
from collections import Counter

INPUT_FILE = "data/sampled_origins.csv"
OUTPUT_FILE = "data/language_data.csv"

# Map file extensions to language names (top ~60 languages)
EXTENSION_TO_LANG = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++",
    ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin", ".kts": "Kotlin",
    ".scala": "Scala", ".m": "Objective-C", ".mm": "Objective-C++",
    ".r": "R", ".R": "R", ".pl": "Perl", ".pm": "Perl",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".lua": "Lua", ".dart": "Dart", ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hrl": "Erlang", ".hs": "Haskell",
    ".ml": "OCaml", ".mli": "OCaml", ".fs": "F#", ".fsx": "F#",
    ".clj": "Clojure", ".cljs": "ClojureScript",
    ".jl": "Julia", ".v": "Verilog", ".vhd": "VHDL", ".vhdl": "VHDL",
    ".asm": "Assembly", ".s": "Assembly", ".S": "Assembly",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sass": "Sass", ".less": "Less", ".vue": "Vue",
    ".sql": "SQL", ".f": "Fortran", ".f90": "Fortran", ".f95": "Fortran",
    ".pas": "Pascal", ".pp": "Pascal", ".d": "D",
    ".nim": "Nim", ".zig": "Zig", ".cmake": "CMake",
    ".tf": "HCL", ".hcl": "HCL", ".yaml": "YAML", ".yml": "YAML",
    ".json": "JSON", ".xml": "XML", ".toml": "TOML",
    ".md": "Markdown", ".rst": "reStructuredText",
    ".ipynb": "Jupyter Notebook", ".rmd": "R Markdown",
    ".ps1": "PowerShell", ".bat": "Batch", ".cmd": "Batch",
    ".groovy": "Groovy", ".gradle": "Groovy",
    ".coffee": "CoffeeScript", ".elm": "Elm",
    ".svelte": "Svelte", ".sol": "Solidity",
}


def fetch_github_languages(repo_full_name, session):
    """Fetch language byte counts from GitHub API."""
    url = f"https://api.github.com/repos/{repo_full_name}/languages"
    response = session.get(url)

    if response.status_code == 403:
        # Rate limited
        reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
        wait = max(reset_time - time.time(), 0) + 5
        print(f"\n  GitHub rate limited. Waiting {wait:.0f}s...")
        time.sleep(wait)
        response = session.get(url)

    if response.status_code == 404:
        return None, "not_found"
    if response.status_code != 200:
        return None, f"error_{response.status_code}"

    languages = response.json()
    if not languages:
        return None, "no_languages"

    return languages, "ok"


def fetch_swh_file_extensions(origin_url, swh_session):
    """Fetch file listing from the latest SWH snapshot and analyze extensions."""
    # Get the latest visit with a snapshot
    encoded_url = requests.utils.quote(origin_url, safe="")
    visits_url = f"https://archive.softwareheritage.org/api/1/origin/{encoded_url}/visits/"

    response = swh_session.get(visits_url, params={"per_page": 10})

    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 60))
        time.sleep(retry_after + 1)
        response = swh_session.get(visits_url, params={"per_page": 10})

    if response.status_code != 200:
        return None

    visits = response.json()
    # Find a visit with a snapshot
    snapshot_id = None
    for visit in visits:
        if visit.get("snapshot"):
            snapshot_id = visit["snapshot"]
            break

    if not snapshot_id:
        return None

    # Get snapshot branches (to find HEAD / main branch)
    snap_url = f"https://archive.softwareheritage.org/api/1/snapshot/{snapshot_id}/"
    time.sleep(3.5)
    response = swh_session.get(snap_url)

    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 60))
        time.sleep(retry_after + 1)
        response = swh_session.get(snap_url)

    if response.status_code != 200:
        return None

    snapshot_data = response.json()
    branches = snapshot_data.get("branches", {})

    # Find HEAD or main/master branch
    target_id = None
    for branch_name in ["HEAD", "refs/heads/main", "refs/heads/master"]:
        branch = branches.get(branch_name)
        if branch and branch.get("target_type") == "revision":
            target_id = branch["target"]
            break
        elif branch and branch.get("target_type") == "alias":
            alias_target = branch.get("target")
            alias_branch = branches.get(alias_target)
            if alias_branch and alias_branch.get("target_type") == "revision":
                target_id = alias_branch["target"]
                break

    if not target_id:
        return None

    # Get the directory of the revision
    time.sleep(3.5)
    rev_url = f"https://archive.softwareheritage.org/api/1/revision/{target_id}/"
    response = swh_session.get(rev_url)

    if response.status_code != 200:
        return None

    rev_data = response.json()
    dir_id = rev_data.get("directory")
    if not dir_id:
        return None

    # Get directory listing
    time.sleep(3.5)
    dir_url = f"https://archive.softwareheritage.org/api/1/directory/{dir_id}/"
    response = swh_session.get(dir_url)

    if response.status_code != 200:
        return None

    entries = response.json()
    ext_counts = Counter()
    for entry in entries:
        if entry.get("type") == "file":
            name = entry.get("name", "")
            dot_pos = name.rfind(".")
            if dot_pos > 0:
                ext = name[dot_pos:].lower()
                if ext in EXTENSION_TO_LANG:
                    ext_counts[EXTENSION_TO_LANG[ext]] += 1

    if not ext_counts:
        return None

    return dict(ext_counts)


def determine_primary_language(github_langs, swh_langs):
    """Pick the primary language from available data."""
    if github_langs:
        # GitHub gives byte counts — the top one is primary
        primary = max(github_langs, key=github_langs.get)
        total_bytes = sum(github_langs.values())
        return primary, github_langs.get(primary, 0) / total_bytes if total_bytes else 0

    if swh_langs:
        primary = max(swh_langs, key=swh_langs.get)
        total_files = sum(swh_langs.values())
        return primary, swh_langs.get(primary, 0) / total_files if total_files else 0

    return None, 0


def load_existing_progress(output_file):
    """Load already-fetched URLs to support resuming."""
    if os.path.isfile(output_file):
        existing = pd.read_csv(output_file)
        return set(existing["url"].tolist())
    return set()


def main():
    parser = argparse.ArgumentParser(description="Fetch language data for sampled origins")
    parser.add_argument("--github-token", type=str, default=None,
                        help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--swh-token", type=str, default=None,
                        help="SWH API token (or set SWH_API_TOKEN env var)")
    parser.add_argument("--skip-swh", action="store_true",
                        help="Skip SWH file extension analysis (faster, GitHub only)")
    args = parser.parse_args()

    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    swh_token = args.swh_token or os.environ.get("SWH_API_TOKEN")

    if not github_token:
        print("Warning: No GitHub token provided. Rate limit will be 60 req/hr.")
        print("Set GITHUB_TOKEN env var or pass --github-token for 5000 req/hr.")
        print("Create a token at: https://github.com/settings/tokens\n")

    # Load sampled origins
    if not os.path.isfile(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run sample_origins.py first.")
        return

    sampled = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(sampled):,} sampled origins from {INPUT_FILE}")

    # Set up sessions
    gh_session = requests.Session()
    gh_session.headers["Accept"] = "application/vnd.github.v3+json"
    if github_token:
        gh_session.headers["Authorization"] = f"token {github_token}"
        print("Using authenticated GitHub requests (5000 req/hr)")
    else:
        print("Using unauthenticated GitHub requests (60 req/hr)")

    swh_session = requests.Session()
    if swh_token:
        swh_session.headers["Authorization"] = f"Bearer {swh_token}"

    # Load progress for resuming
    done_urls = load_existing_progress(OUTPUT_FILE)
    if done_urls:
        print(f"Resuming: {len(done_urls):,} origins already fetched, skipping them.")

    remaining = sampled[~sampled["url"].isin(done_urls)]
    print(f"Origins to fetch: {len(remaining):,}")

    if len(remaining) == 0:
        print("All origins already fetched!")
        return

    results = []
    write_header = not os.path.isfile(OUTPUT_FILE)
    github_errors = 0
    swh_fetched = 0

    for _, row in tqdm(remaining.iterrows(), total=len(remaining), desc="Fetching languages"):
        origin_url = row["url"]
        repo_full_name = row.get("repo_full_name", origin_url.replace("https://github.com/", ""))

        # 1. GitHub API
        github_langs, status = fetch_github_languages(repo_full_name, gh_session)
        if status not in ("ok", "no_languages"):
            github_errors += 1

        # 2. SWH file extensions (only if GitHub failed and --skip-swh not set)
        swh_langs = None
        if not github_langs and not args.skip_swh:
            swh_langs = fetch_swh_file_extensions(origin_url, swh_session)
            if swh_langs:
                swh_fetched += 1

        # Determine primary language
        primary_lang, lang_ratio = determine_primary_language(github_langs, swh_langs)

        record = {
            "url": origin_url,
            "repo_full_name": repo_full_name,
            "primary_language": primary_lang,
            "primary_language_ratio": round(lang_ratio, 4),
            "github_languages": str(github_langs) if github_langs else "",
            "swh_languages": str(swh_langs) if swh_langs else "",
            "language_source": "github" if github_langs else ("swh" if swh_langs else "unknown"),
            "github_status": status,
        }
        results.append(record)

        # Write in batches of 100
        if len(results) >= 100:
            batch_df = pd.DataFrame(results)
            batch_df.to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)
            write_header = False
            results = []

        # Rate limiting for GitHub (authenticated: ~1.4 req/s is safe)
        if github_token:
            time.sleep(0.75)
        else:
            time.sleep(60)  # Very slow without token

    # Write remaining
    if results:
        batch_df = pd.DataFrame(results)
        batch_df.to_csv(OUTPUT_FILE, mode="a", header=write_header, index=False)

    # Summary
    if os.path.isfile(OUTPUT_FILE):
        final = pd.read_csv(OUTPUT_FILE)
        print(f"\nDone! Total records in {OUTPUT_FILE}: {len(final):,}")
        print(f"GitHub API errors: {github_errors}")
        print(f"SWH fallback used: {swh_fetched}")
        print(f"\nLanguage distribution (top 15):")
        print(final["primary_language"].value_counts().head(15).to_string())


if __name__ == "__main__":
    main()
