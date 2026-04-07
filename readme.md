## Software Heritage Analysis (COSC 540)

Analyzing programming language evolution and project lifecycles via the Software Heritage Archive.

### Setup

Create the conda environment:

```bash
conda env create -f environment.yml
conda activate softwereproject
```

### Pipeline

Run the scripts in order from the project root directory:

#### Step 0: Collect Origins

`src/get_origins.py` paginates through the Software Heritage `/origins/` API to collect project URLs. This was run over multiple days, collecting **10.7 million origins** stored in `data/link_store.csv` (1.6 GB). Supports resume — saves progress on Ctrl-C and picks up where it left off.

```bash
python src/get_origins.py origins.txt
```

**Output:** `data/link_store.csv` (10,715,000 origins)

#### Step 1: Sample Origins

Filters to GitHub-only origins (10M+) and draws a random sample of 20,000 projects.

```bash
python src/sample_origins.py
```

**Output:** `data/sampled_origins.csv`

#### Step 2: Fetch Visit Data (SWH API)

Fetches visit history for each sampled project to determine project lifecycle (first seen, last active, activity frequency). Supports resuming — safe to Ctrl-C and restart.

```bash
# Without token (~1200 req/hr)
python src/fetch_visits.py

# With SWH token (faster, get one at https://archive.softwareheritage.org/)
python src/fetch_visits.py --token YOUR_SWH_TOKEN
```

**Output:** `data/visit_data.csv`

#### Step 3: Fetch Language Data (GitHub GraphQL API)

Detects primary language per project using GitHub's GraphQL API. Queries 50 repos per request, so 20K repos completes in ~30 minutes. A GitHub personal access token is required — create one at https://github.com/settings/tokens (no special scopes needed).

```bash
python src/fetch_languages_graphql.py --github-token YOUR_GITHUB_TOKEN
```

**Output:** `data/language_data.csv`

### Data Files

- `data/link_store.csv`: ~10.7M origins with URLs and visit endpoints (1.6 GB)
- `data/sampled_origins.csv`: 20K sampled GitHub origins
- `data/visit_data.csv`: Visit history per project
- `data/language_data.csv`: Language data per project
