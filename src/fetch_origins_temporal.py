"""
Collect Software Heritage origins with explicit temporal balance using
actual commit dates — not metadata text — to assign each origin to a
decade bucket.

Two-phase discovery:
  Phase 1 — Historical forges
    Enumerates origins directly from forges known to host old software
    (GNU Savannah, non-GNU Savannah, SourceForge) via the
    /api/1/origin/search/{pattern}/ endpoint.  These are processed first
    to fill the older decade buckets (pre-1990, 1990s, 2000s).

  Phase 2 — Metadata-search sweep
    Uses randomly shuffled year/month strings (1970–2025) as fulltext
    queries against /api/1/origin/metadata-search/ to discover origins
    on mainstream forges (GitHub, GitLab, …).  Results are filtered to
    git forge URLs immediately, before any API navigation, to avoid the
    package registries that dominate metadata-search results.

Decade buckets (based on first_commit_date_approx):
    pre_1990  — commits before 1990
    1990s     — 1990–1999
    2000s     — 2000–2009
    2010s     — 2010–2019
    2020s     — 2020 onward

Each bucket has an equal share of the target (target // 5).  The script
skips origins whose bucket is already full and stops when all five buckets
reach their quota (or all queries are exhausted).

Per-origin pipeline (GraphQL-first, REST fallback):
  1. SWH GraphQL  — origin → visits + HEAD revision (date, swhid) + directory
  2. SWH GraphQL  — revision log, paginated, for commit count and oldest date
  3. SWH GraphQL  — directory entries for language detection
  4. REST         — fallback for any step that returns nothing

Resume support:
  On restart, existing rows in the output CSV are read to rebuild bucket
  counts and skip already-processed URLs.

Usage:
    python src/fetch_origins_temporal.py [--token TOKEN] [--target N]
                                         [--log-pages N] [--seed N]

Output: data/temporal_origins.csv
"""

import requests
from requests.exceptions import ConnectionError, Timeout, ChunkedEncodingError
from collections import Counter, OrderedDict
import pandas as pd
import time
import os
import random
import argparse
from datetime import datetime, timezone

BASE_URL    = "https://archive.softwareheritage.org/api/1"
GQL_URL     = "https://archive.softwareheritage.org/graphql/"
OUTPUT_FILE = "data/temporal_origins.csv"

MIN_COMMITS       = 50
ABANDON_DAYS      = 365
TARGET_DEFAULT    = 5000
LOG_PAGES_DEFAULT = 10
MAX_RETRIES       = 5
REQUEST_TIMEOUT   = 30
RATE_UNAUTH       = 3.2   # ≈1 200 req/hr unauthenticated
RATE_AUTH         = 3.0   # 1 200 req/hr authenticated (3 s between calls)

# ---------------------------------------------------------------------------
# Decade buckets
# ---------------------------------------------------------------------------
# Keys are used as column values in the CSV.
DECADE_BUCKETS = OrderedDict([
    ("pre_1990", (None, 1990)),
    ("1990s",    (1990, 2000)),
    ("2000s",    (2000, 2010)),
    ("2010s",    (2010, 2020)),
    ("2020s",    (2020, None)),
])


def get_bucket(commit_date) -> str | None:
    """Return the decade bucket key for a commit date, or None if date is missing."""
    if commit_date is None:
        return None
    y = commit_date.year
    for key, (lo, hi) in DECADE_BUCKETS.items():
        if (lo is None or y >= lo) and (hi is None or y < hi):
            return key
    return None


def bucket_summary(counts: dict, per_bucket: int) -> str:
    parts = []
    for key in DECADE_BUCKETS:
        n = counts.get(key, 0)
        tick = "✓" if n >= per_bucket else ""
        parts.append(f"{key}={n}/{per_bucket}{tick}")
    return "  Buckets: " + " | ".join(parts)


def all_full(counts: dict, per_bucket: int) -> bool:
    return all(counts.get(k, 0) >= per_bucket for k in DECADE_BUCKETS)


# ---------------------------------------------------------------------------
# Forge lists
# ---------------------------------------------------------------------------
# Phase-1 forges: enumerated directly for their reliable historical depth.
HISTORICAL_FORGE_PATTERNS = [
    "savannah.gnu.org",        # GNU projects — often 1980s/90s
    "savannah.nongnu.org",     # non-GNU free software — similar era
    "sourceforge.net/p/",      # projects from 1999 onward
]

# Phase-2 URL allowlist: metadata-search results outside this set are
# package registries with no git revision structure.
GIT_FORGE_PATTERNS = (
    "github.com/",
    "gitlab.com/",
    "bitbucket.org/",
    "sourceforge.net/p/",
    "savannah.gnu.org/",
    "savannah.nongnu.org/",
    "codeberg.org/",
    "launchpad.net/",
    "sr.ht/",
    "framagit.org/",
    "salsa.debian.org/",
    "gitlab.freedesktop.org/",
    "invent.kde.org/",
)

FORGE_DISPLAY = [
    ("github.com",       "github"),
    ("gitlab.com",       "gitlab"),
    ("bitbucket.org",    "bitbucket"),
    ("sourceforge.net",  "sourceforge"),
    ("codeberg.org",     "codeberg"),
    ("launchpad.net",    "launchpad"),
    ("savannah.",        "savannah"),
    ("sr.ht",            "sourcehut"),
    ("framagit.org",     "framagit"),
    ("salsa.debian.org", "salsa"),
    ("freedesktop.org",  "freedesktop"),
    ("kde.org",          "kde"),
]

EXTENSION_TO_LANG = {
    ".py": "Python",      ".js": "JavaScript",   ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript",  ".java": "Java",
    ".c": "C",   ".h": "C",   ".cpp": "C++",   ".cc": "C++",
    ".cxx": "C++", ".hpp": "C++", ".hh": "C++", ".cs": "C#",
    ".go": "Go",  ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift",    ".kt": "Kotlin",       ".kts": "Kotlin",
    ".scala": "Scala",    ".m": "Objective-C",   ".mm": "Objective-C++",
    ".r": "R",    ".R": "R",    ".pl": "Perl",   ".pm": "Perl",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".lua": "Lua",  ".dart": "Dart",  ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hrl": "Erlang", ".hs": "Haskell",
    ".ml": "OCaml", ".mli": "OCaml", ".fs": "F#", ".fsx": "F#",
    ".clj": "Clojure",    ".cljs": "ClojureScript",
    ".jl": "Julia", ".v": "Verilog", ".vhd": "VHDL", ".vhdl": "VHDL",
    ".asm": "Assembly", ".s": "Assembly", ".S": "Assembly",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sass": "Sass", ".less": "Less", ".vue": "Vue",
    ".sql": "SQL", ".f": "Fortran", ".f90": "Fortran", ".f95": "Fortran",
    ".pas": "Pascal", ".pp": "Pascal", ".d": "D",
    ".nim": "Nim",  ".zig": "Zig",  ".tf": "HCL",  ".hcl": "HCL",
    ".ps1": "PowerShell", ".bat": "Batch",
    ".groovy": "Groovy",  ".coffee": "CoffeeScript",
    ".elm": "Elm", ".svelte": "Svelte", ".sol": "Solidity",
    ".ipynb": "Jupyter Notebook",
}

# ---------------------------------------------------------------------------
# GraphQL query strings
# ---------------------------------------------------------------------------

GQL_ORIGIN_DATA = """
query GetOriginData($url: String!) {
  origin(url: $url) {
    visits(first: 1000) {
      nodes {
        date
        status
        snapshot { swhid }
      }
      pageInfo { hasNextPage }
    }
    latestVisit {
      snapshot {
        branches(first: 100) {
          nodes {
            name
            targetType
            target {
              ...on Revision {
                swhid
                date
                directory { swhid }
              }
            }
          }
        }
      }
    }
  }
}
"""

GQL_REVISION_LOG = """
query GetRevisionLog($swhid: ID!, $after: String) {
  revision(swhid: $swhid) {
    revisionLog(first: 100, after: $after) {
      nodes { date }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

GQL_DIRECTORY = """
query GetDirectory($swhid: ID!) {
  directory(swhid: $swhid) {
    entries(first: 100) {
      nodes {
        name
        target {
          ...on Content {
            swhid
            language { lang }
          }
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_git_forge(url: str) -> bool:
    return any(p in url for p in GIT_FORGE_PATTERNS)


def categorize_forge(url: str) -> str:
    for fragment, name in FORGE_DISPLAY:
        if fragment in url:
            return name
    return "other"


def swhid_to_hash(swhid: str) -> str | None:
    return swhid.split(":")[-1] if swhid else None


def to_swhid(obj_type: str, hash_hex: str) -> str:
    codes = {"revision": "rev", "directory": "dir", "content": "cnt", "snapshot": "snp"}
    return f"swh:1:{codes.get(obj_type, obj_type)}:{hash_hex}"


def parse_utc(date_str):
    if not date_str:
        return None
    try:
        return pd.to_datetime(date_str, utc=True)
    except Exception:
        return None


def next_link(response) -> str | None:
    header = response.headers.get("Link", "")
    if 'rel="next"' not in header:
        return None
    for part in header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _parse_retry_after(response) -> int:
    """Return seconds to wait from a 429 response.

    Checks Retry-After (seconds or HTTP-date) then X-RateLimit-Reset
    (Unix timestamp) as fallback, defaulting to 60 s.
    """
    header = response.headers.get("Retry-After", "")
    if header.isdigit():
        return int(header)
    if header:
        # HTTP-date format: "Wed, 21 Oct 2025 07:28:00 GMT"
        try:
            from email.utils import parsedate_to_datetime
            reset_dt = parsedate_to_datetime(header)
            wait = int((reset_dt - datetime.now(timezone.utc)).total_seconds())
            return max(wait, 1)
        except Exception:
            pass
    reset_ts = response.headers.get("X-RateLimit-Reset", "")
    if reset_ts.isdigit():
        wait = int(int(reset_ts) - time.time())
        return max(wait, 1)
    return 60


def _print_rate_limit(wait_seconds: int, prefix: str = ""):
    resume_at = datetime.now(timezone.utc).replace(microsecond=0)
    resume_at = pd.Timestamp(resume_at) + pd.Timedelta(seconds=wait_seconds + 1)
    mins, secs = divmod(wait_seconds, 60)
    duration   = f"{mins}m {secs}s" if mins else f"{secs}s"
    tag = f"[{prefix}] " if prefix else ""
    print(f"\n  {tag}Rate limited — pausing {duration}. "
          f"Resuming at {resume_at.strftime('%H:%M:%S')} UTC")


def safe_get(session, url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except (ConnectionError, Timeout, ChunkedEncodingError):
            if attempt == MAX_RETRIES:
                return None
            time.sleep(10 * attempt)
            continue
        if resp.status_code == 429:
            wait = _parse_retry_after(resp)
            _print_rate_limit(wait, prefix="REST")
            time.sleep(wait + 1)
            continue
        return resp
    return None


def graphql_post(session, query: str, variables: dict):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(
                GQL_URL,
                json={"query": query, "variables": variables},
                timeout=REQUEST_TIMEOUT,
            )
        except (ConnectionError, Timeout, ChunkedEncodingError):
            if attempt == MAX_RETRIES:
                return None
            time.sleep(10 * attempt)
            continue
        if resp.status_code == 429:
            wait = _parse_retry_after(resp)
            _print_rate_limit(wait, prefix="GQL")
            time.sleep(wait + 1)
            continue
        if resp.status_code != 200:
            return None
        body = resp.json()
        if "errors" in body and not body.get("data"):
            return None
        return body.get("data")
    return None


# ---------------------------------------------------------------------------
# GraphQL data functions
# ---------------------------------------------------------------------------

def gql_get_origin_data(url: str, session):
    """
    One GraphQL call: visits + HEAD revision + directory.
    Returns (visit_metrics dict, head dict) or (None, None).
    """
    data = graphql_post(session, GQL_ORIGIN_DATA, {"url": url})
    if not data:
        return None, None
    origin = data.get("origin") or {}
    if not origin:
        return None, None

    # Visit metrics
    visits_data = (origin.get("visits") or {}).get("nodes") or []
    has_more    = (origin.get("visits") or {}).get("pageInfo", {}).get("hasNextPage", False)
    dates = sorted(filter(None, (parse_utc(v.get("date")) for v in visits_data)))
    first_v = dates[0] if dates else None
    last_v  = dates[-1] if dates else None
    now     = datetime.now(timezone.utc)
    lifespan_days   = int((last_v - first_v).total_seconds() / 86400) if first_v and last_v else 0
    days_since_last = int((now - last_v).total_seconds() / 86400) if last_v else None

    visit_metrics = {
        "num_visits":               len(visits_data),
        "num_visits_is_lower_bound": has_more,
        "num_snapshots":            sum(1 for v in visits_data
                                        if (v.get("snapshot") or {}).get("swhid")),
        "first_visit_date":         str(first_v) if first_v else None,
        "last_visit_date":          str(last_v)  if last_v  else None,
        "lifespan_days":            lifespan_days,
        "days_since_last_visit":    days_since_last,
        "is_abandoned":             int(days_since_last is not None
                                        and days_since_last > ABANDON_DAYS),
    }

    # HEAD revision
    branches = (
        (origin.get("latestVisit") or {})
        .get("snapshot", {})
        .get("branches", {})
        .get("nodes") or []
    )
    revision = None
    for priority in ("HEAD", "refs/heads/main", "refs/heads/master"):
        for branch in branches:
            if branch.get("name") == priority:
                t = branch.get("target") or {}
                if (t.get("swhid") or "").startswith("swh:1:rev:"):
                    revision = t
                    break
        if revision:
            break
    if not revision:
        for branch in branches:
            t = branch.get("target") or {}
            if (t.get("swhid") or "").startswith("swh:1:rev:"):
                revision = t
                break
    if not revision:
        return visit_metrics, None

    head = {
        "revision_swhid":   revision["swhid"],
        "head_commit_date": parse_utc(revision.get("date")),
        "directory_swhid":  (revision.get("directory") or {}).get("swhid"),
    }
    return visit_metrics, head


def gql_fetch_commit_log(rev_swhid: str, session, rate_pause: float, max_pages: int):
    oldest = None
    commit_count = 0
    pages = 0
    cursor = None
    reached_end = False
    while pages < max_pages:
        time.sleep(rate_pause)
        data = graphql_post(session, GQL_REVISION_LOG,
                            {"swhid": rev_swhid, "after": cursor})
        if not data:
            break
        log = (data.get("revision") or {}).get("revisionLog") or {}
        for commit in log.get("nodes") or []:
            commit_count += 1
            d = parse_utc(commit.get("date"))
            if d is not None and (oldest is None or d < oldest):
                oldest = d
        pages += 1
        page_info = log.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            reached_end = True
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            reached_end = True
            break
    return oldest, commit_count, pages, reached_end


def gql_detect_language(dir_swhid: str, session):
    data = graphql_post(session, GQL_DIRECTORY, {"swhid": dir_swhid})
    if not data:
        return None, "gql_error"
    entries = ((data.get("directory") or {}).get("entries") or {}).get("nodes") or []
    ext_counts = Counter()
    swh_langs  = []
    for entry in entries:
        name   = entry.get("name", "")
        target = entry.get("target") or {}
        dot = name.rfind(".")
        if dot > 0:
            ext = name[dot:].lower()
            if ext in EXTENSION_TO_LANG:
                ext_counts[EXTENSION_TO_LANG[ext]] += 1
        lang_obj = target.get("language")
        if lang_obj and lang_obj.get("lang"):
            swh_langs.append(lang_obj["lang"])
    if ext_counts:
        return max(ext_counts, key=ext_counts.get), "extension"
    if swh_langs:
        return Counter(swh_langs).most_common(1)[0][0], "swh_content_api"
    return None, "unknown"


# ---------------------------------------------------------------------------
# REST fallbacks
# ---------------------------------------------------------------------------

def rest_fetch_visits(origin_url: str, session, rate_pause: float = 3.0):
    encoded = requests.utils.quote(origin_url, safe="")
    url = f"{BASE_URL}/origin/{encoded}/visits/"
    all_visits = []
    first_page = True
    while url:
        if not first_page:
            time.sleep(rate_pause)
        first_page = False
        resp = safe_get(session, url, params={"per_page": 1000})
        if resp is None or resp.status_code != 200:
            return None
        all_visits.extend(resp.json())
        url = next_link(resp)
    return all_visits


def rest_get_head_revision(snapshot_id: str, session, rate_pause: float = 3.0):
    resp = safe_get(session, f"{BASE_URL}/snapshot/{snapshot_id}/")
    if resp is None or resp.status_code != 200:
        return None
    branches = resp.json().get("branches") or {}
    revision_id = None
    for name in ("HEAD", "refs/heads/main", "refs/heads/master"):
        branch = branches.get(name) or {}
        btype  = branch.get("target_type")
        if btype == "revision":
            revision_id = branch["target"]
            break
        if btype == "alias":
            alias = branches.get(branch.get("target")) or {}
            if alias.get("target_type") == "revision":
                revision_id = alias["target"]
                break
    if not revision_id:
        for branch in branches.values():
            if isinstance(branch, dict) and branch.get("target_type") == "revision":
                revision_id = branch["target"]
                break
    if not revision_id:
        return None
    time.sleep(rate_pause)
    resp = safe_get(session, f"{BASE_URL}/revision/{revision_id}/")
    if resp is None or resp.status_code != 200:
        return None
    rev = resp.json()
    return {
        "revision_swhid":   to_swhid("revision", revision_id),
        "head_commit_date": parse_utc(rev.get("date")),
        "directory_swhid":  to_swhid("directory", rev["directory"]) if rev.get("directory") else None,
    }


def rest_fetch_commit_log(revision_id: str, session, rate_pause: float, max_pages: int):
    url = f"{BASE_URL}/revision/{revision_id}/log/"
    oldest = None
    commit_count = 0
    pages = 0
    reached_end = False
    while url and pages < max_pages:
        time.sleep(rate_pause)
        resp = safe_get(session, url, params={"per_page": 100})
        if resp is None or resp.status_code != 200:
            break
        for commit in resp.json():
            commit_count += 1
            d = parse_utc(commit.get("date"))
            if d is not None and (oldest is None or d < oldest):
                oldest = d
        pages += 1
        nxt = next_link(resp)
        if nxt is None:
            reached_end = True
            break
        url = nxt
    return oldest, commit_count, pages, reached_end


def rest_detect_language(directory_id: str, session, rate_pause: float):
    resp = safe_get(session, f"{BASE_URL}/directory/{directory_id}/")
    if resp is None or resp.status_code != 200:
        return None, "error"
    ext_counts     = Counter()
    sha1_candidates = []
    for entry in resp.json():
        if entry.get("type") != "file":
            continue
        name = entry.get("name", "")
        dot  = name.rfind(".")
        if dot > 0:
            ext = name[dot:].lower()
            if ext in EXTENSION_TO_LANG:
                ext_counts[EXTENSION_TO_LANG[ext]] += 1
        if "sha1" in (entry.get("checksums") or {}):
            sha1_candidates.append(entry["checksums"]["sha1"])
    if ext_counts:
        return max(ext_counts, key=ext_counts.get), "extension"
    for sha1 in sha1_candidates[:5]:
        time.sleep(rate_pause)
        lang_resp = safe_get(session, f"{BASE_URL}/content/sha1:{sha1}/language/")
        if lang_resp and lang_resp.status_code == 200:
            lang = lang_resp.json().get("lang")
            if lang:
                return lang, "swh_content_api"
    return None, "unknown"


def compute_visit_metrics_rest(visits: list) -> dict:
    dates = sorted(filter(None, (parse_utc(v.get("date")) for v in visits)))
    first_v = dates[0] if dates else None
    last_v  = dates[-1] if dates else None
    now     = datetime.now(timezone.utc)
    lifespan   = int((last_v - first_v).total_seconds() / 86400) if first_v and last_v else 0
    days_since = int((now - last_v).total_seconds() / 86400) if last_v else None
    return {
        "num_visits":               len(visits),
        "num_visits_is_lower_bound": False,
        "num_snapshots":            sum(1 for v in visits if v.get("snapshot")),
        "first_visit_date":         str(first_v) if first_v else None,
        "last_visit_date":          str(last_v)  if last_v  else None,
        "lifespan_days":            lifespan,
        "days_since_last_visit":    days_since,
        "is_abandoned":             int(days_since is not None and days_since > ABANDON_DAYS),
    }


# ---------------------------------------------------------------------------
# Per-origin pipeline (GraphQL-first, REST fallback)
# ---------------------------------------------------------------------------

def process_origin(url: str, session, rate_pause: float, log_pages: int):
    """
    Run the full pipeline for one origin URL.

    Returns a record dict on success, or None if the origin should be skipped
    (no resolvable revision, or fewer than MIN_COMMITS commits).
    """
    # Step 1: origin data via GraphQL
    time.sleep(rate_pause)
    visit_metrics, head = gql_get_origin_data(url, session)

    # REST fallback for visit metrics
    if visit_metrics is None:
        visits_raw = rest_fetch_visits(url, session, rate_pause)
        time.sleep(rate_pause)
        visit_metrics = compute_visit_metrics_rest(visits_raw or [])

    # REST fallback for HEAD revision
    if head is None:
        visits_raw = rest_fetch_visits(url, session, rate_pause)
        time.sleep(rate_pause)
        if visits_raw:
            for v in sorted(visits_raw, key=lambda x: x.get("date", ""), reverse=True):
                snap_id = v.get("snapshot")
                if snap_id:
                    time.sleep(rate_pause)
                    head = rest_get_head_revision(snap_id, session, rate_pause)
                    if head:
                        break

    if head is None:
        return None

    # Step 2: commit log (GraphQL, REST fallback)
    time.sleep(rate_pause)
    rev_swhid = head["revision_swhid"]
    first_commit, commit_count, log_pages_used, reached_end = \
        gql_fetch_commit_log(rev_swhid, session, rate_pause, log_pages)

    if commit_count == 0:
        revision_hash = swhid_to_hash(rev_swhid)
        if revision_hash:
            first_commit, commit_count, log_pages_used, reached_end = \
                rest_fetch_commit_log(revision_hash, session, rate_pause, log_pages)

    if commit_count == 0 or (reached_end and commit_count < MIN_COMMITS):
        return None

    # Step 3: language detection (GraphQL, REST fallback)
    lang, lang_source = None, "no_directory"
    dir_swhid = head["directory_swhid"]
    if dir_swhid:
        time.sleep(rate_pause)
        lang, lang_source = gql_detect_language(dir_swhid, session)
        if lang is None and lang_source == "gql_error":
            dir_hash = swhid_to_hash(dir_swhid)
            if dir_hash:
                lang, lang_source = rest_detect_language(dir_hash, session, rate_pause)

    head_date = str(head["head_commit_date"]) if head["head_commit_date"] else None
    commit_label = str(commit_count) if reached_end else f"≥{commit_count}"

    return {
        "url":                      url,
        "forge":                    categorize_forge(url),
        "primary_language":         lang,
        "language_source":          lang_source,
        "head_commit_date":         head_date,
        "first_commit_date_approx": str(first_commit) if first_commit else None,
        "commit_count":             commit_label,
        "commit_log_pages":         log_pages_used,
        "commit_log_reached_end":   reached_end,
        **visit_metrics,
    }


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def origin_search_by_pattern(pattern: str, session, rate_pause: float,
                             max_origins: int = 5000):
    """
    Enumerate origins whose URL contains `pattern` via
    GET /api/1/origin/search/{encoded_pattern}/
    Returns a list of origin URL strings (up to max_origins).
    Pauses rate_pause seconds between pages to respect API limits.
    """
    encoded = requests.utils.quote(pattern, safe="")
    url = f"{BASE_URL}/origin/search/{encoded}/"
    urls = []
    while url and len(urls) < max_origins:
        resp = safe_get(session, url)
        if resp is None or resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        for item in batch:
            if isinstance(item, dict):
                u = item.get("url", "")
            else:
                u = str(item)
            if u:
                urls.append(u)
        url = next_link(resp)
        if url:
            time.sleep(rate_pause)
    return urls


def metadata_search(query: str, session, limit: int = 1000) -> list:
    resp = safe_get(session, f"{BASE_URL}/origin/metadata-search/",
                    params={"fulltext": query, "limit": limit})
    if resp is None or resp.status_code != 200:
        return []
    data = resp.json()
    return data if isinstance(data, list) else data.get("results", [])


def generate_date_queries(start_year=1970, end_year=2025, seed=42):
    queries = []
    for year in range(start_year, end_year + 1):
        queries.append(str(year))
        for month in range(1, 13):
            queries.append(f"{year}-{month:02d}")
    random.Random(seed).shuffle(queries)
    return queries


# ---------------------------------------------------------------------------
# Progress persistence
# ---------------------------------------------------------------------------

def load_existing(output_file: str):
    """Return (done_url_set, bucket_counts_dict) from an existing output CSV."""
    done_urls     = set()
    bucket_counts = {k: 0 for k in DECADE_BUCKETS}
    if not os.path.isfile(output_file):
        return done_urls, bucket_counts
    try:
        df = pd.read_csv(output_file, usecols=["url", "first_commit_date_approx"])
        done_urls = set(df["url"].dropna())
        for date_str in df["first_commit_date_approx"].dropna():
            b = get_bucket(parse_utc(date_str))
            if b:
                bucket_counts[b] = bucket_counts.get(b, 0) + 1
    except Exception:
        pass
    return done_urls, bucket_counts


def flush(records: list, output_file: str, write_header: bool):
    pd.DataFrame(records).to_csv(output_file, mode="a", header=write_header, index=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Collect SWH origins with explicit decade-balanced temporal coverage"
    )
    parser.add_argument("--token",     type=str, default=None,
                        help="SWH API token (or set SWH_API_TOKEN env var)")
    parser.add_argument("--target",    type=int, default=TARGET_DEFAULT,
                        help=f"Total target origins across all buckets (default: {TARGET_DEFAULT})")
    parser.add_argument("--log-pages", type=int, default=LOG_PAGES_DEFAULT,
                        help=f"Max commit-log pages per origin, 100 commits each "
                             f"(default: {LOG_PAGES_DEFAULT})")
    parser.add_argument("--seed",      type=int, default=42,
                        help="Random seed for metadata-search query shuffle (default: 42)")
    args = parser.parse_args()

    token = args.token or os.environ.get("SWH_API_TOKEN")
    session = requests.Session()
    session.headers["Content-Type"] = "application/json"
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
        rate_pause = RATE_AUTH
        print("Authenticated SWH session — ~3.0 s between requests")
    else:
        rate_pause = RATE_UNAUTH
        print("Unauthenticated SWH session — ~3.2 s between requests")
        print("Tip: pass --token or set SWH_API_TOKEN for faster collection")

    os.makedirs("data", exist_ok=True)
    done_urls, bucket_counts = load_existing(OUTPUT_FILE)
    write_header = not os.path.isfile(OUTPUT_FILE)
    collected    = sum(bucket_counts.values())
    per_bucket   = max(1, args.target // len(DECADE_BUCKETS))

    print(f"\nPer-bucket target : {per_bucket} origins  ({len(DECADE_BUCKETS)} buckets × {per_bucket})")
    print(f"Commit log depth  : {args.log_pages} pages × 100 commits")
    print(f"Already collected : {collected:,} origins\n")
    print(bucket_summary(bucket_counts, per_bucket))
    print()

    pending = []

    def try_accept(record, label=""):
        """Check bucket quota, print result, buffer record. Returns True if accepted."""
        nonlocal collected, write_header
        date_str = record.get("first_commit_date_approx")
        bucket   = get_bucket(parse_utc(date_str))
        if bucket is None:
            return False
        if bucket_counts.get(bucket, 0) >= per_bucket:
            return False   # bucket full — skip
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        collected += 1
        pending.append(record)
        print(
            f"  [{collected}] {record['url']}"
            f" | bucket={bucket}"
            f" | commits={record['commit_count']}"
            f" | lang={record['primary_language']}"
            f" | first≈{(date_str or '')[:10]}"
            f" | head={str(record.get('head_commit_date',''))[:10]}"
            + (f"  {label}" if label else "")
        )
        if len(pending) >= 10:
            flush(pending, OUTPUT_FILE, write_header)
            write_header = False
            pending.clear()
            print(bucket_summary(bucket_counts, per_bucket))
        return True

    # ── Phase 1: Historical forges ─────────────────────────────────────────
    print("=" * 60)
    print("PHASE 1 — Historical forges (Savannah, SourceForge)")
    print("=" * 60)

    for pattern in HISTORICAL_FORGE_PATTERNS:
        if all_full(bucket_counts, per_bucket):
            break
        print(f"\nEnumerating origins matching '{pattern}' ...")
        forge_urls = origin_search_by_pattern(pattern, session, rate_pause)

        random.shuffle(forge_urls)   # randomise to avoid bias within forge
        print(f"  Found {len(forge_urls):,} origins")

        for url in forge_urls:
            if all_full(bucket_counts, per_bucket):
                break
            if url in done_urls or not is_git_forge(url):
                continue
            done_urls.add(url)

            record = process_origin(url, session, rate_pause, args.log_pages)
            if record:
                try_accept(record, label="[phase1]")

    # ── Phase 2: Metadata-search sweep ────────────────────────────────────
    print("\n" + "=" * 60)
    print("PHASE 2 — Metadata-search (GitHub, GitLab, …)")
    print("=" * 60)

    date_queries = generate_date_queries(seed=args.seed)
    print(f"Date queries: {len(date_queries)} (1970–2025, shuffled)\n")

    for query in date_queries:
        if all_full(bucket_counts, per_bucket):
            break

        origins = metadata_search(query, session)
        time.sleep(rate_pause)
        if not origins:
            continue

        git_origins = [
            o for o in origins
            if o.get("url") and o["url"] not in done_urls and is_git_forge(o["url"])
        ]
        skipped = len(origins) - len(git_origins)
        print(f"[query={query!r}] {len(origins)} results → "
              f"{len(git_origins)} git-forge origins ({skipped} non-git skipped)")

        for entry in git_origins:
            if all_full(bucket_counts, per_bucket):
                break
            url = entry["url"]
            done_urls.add(url)

            record = process_origin(url, session, rate_pause, args.log_pages)
            if record:
                try_accept(record)

    # Final flush
    if pending:
        flush(pending, OUTPUT_FILE, write_header)

    print(f"\n{'=' * 60}")
    print(f"Finished. Collected {collected:,} origins.")
    print(bucket_summary(bucket_counts, per_bucket))

    if os.path.isfile(OUTPUT_FILE):
        final = pd.read_csv(OUTPUT_FILE)
        print(f"\nTotal rows in {OUTPUT_FILE}: {len(final):,}")
        if "primary_language" in final.columns:
            print("\nTop languages:")
            print(final["primary_language"].value_counts().head(10).to_string())
        if "forge" in final.columns:
            print("\nForge distribution:")
            print(final["forge"].value_counts().to_string())


if __name__ == "__main__":
    main()
