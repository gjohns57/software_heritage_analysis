# Analyzing Aspects of the Evolution ofProgramming Languages and Usage via the Software Heritage Archive

**Course: COSC 540 — Advanced Software Engineering**

**Authors** — *EECS, University of Tennessee, Knoxville*

| Name | Email |
|------|-------|
| Alamgir Hossain   | mhossa49@vols.utk.edu |
| William Greenwood | wgreenwo@vols.utk.edu |
| Gabriel Johnson   | gjohns57@vols.utk.edu |
| Ervin Pangilinan  | epangili@vols.utk.edu |

### Abstract

Open source software powers much of modern computing, yet many projects on public platforms eventually become inactive. Whether the choice of programming language affects how long a project survives has been studied on a small scale before, but not across many languages at once. In this paper, we revisit the question using the Software Heritage archive, the largest public collection of source code ever assembled. We assemble a survival dataset of 11,756 GitHub projects across 22 programming languages and apply Kaplan-Meier estimation, log-rank tests, and Cox proportional hazards regression to it. Our results show that the choice of programming language has a much smaller effect on project longevity than is sometimes assumed. Median project survival ranges from 2.5 to 5.5 years across all 22 languages, and raw abandonment rates that differ between languages (from 59 percent for Ruby down to 37 percent for TypeScript) become statistically indistinguishable once we control for project age. Cox regression finds no statistically significant effect of language generation, compiled status, memory safety, garbage collection, or commit count on the hazard of abandonment. These findings point toward project-level factors, such as community engagement and organizational backing, as the main drivers of project longevity.

---

### Brief Introduction
This repository contains the complete data-collection, preprocessing, and survival-analysis pipeline used to answer three research questions about the longevity of open-source projects:

| RQ  | Question |
|-----|----------|
| RQ1 | How long do projects survive in different programming languages? |
| RQ2 | Do newer (3rd-generation) languages produce more sustainable projects than older ones? |
| RQ3 | Which languages exhibit the highest abandonment rates? |

The pipeline starts from the full Software Heritage (SWH) `/origins/` endpoint (≈ 10.7 M projects), filters to a random sample of 20 000 GitHub repositories, enriches them with metadata from the SWH API and the GitHub GraphQL API, and applies a six-stage cleaning process that yields a 11 756-project analysis-ready dataset spanning 22 languages.

---


## 1. Repository Layout

```
software_heritage_analysis/
├── src/                          # Data-collection & preprocessing scripts
│   ├── get_origins.py            # Step 0 — paginate SWH /origins/ endpoint
│   ├── sample_origins.py         # Step 1 — random 20 K GitHub sample
│   ├── fetch_visits.py           # Step 2 — SWH visit history
│   ├── fetch_languages_graphql.py# Step 3 — GitHub primary language
│   ├── fetch_languages.py        # (legacy REST variant — not used)
│   ├── fetch_commits.py          # Step 4 — GitHub commit counts
│   ├── preprocess.py             # Step 5 — merge, clean, feature-engineer
│   └── 50_plus_filter.py         # Step 6 — keep languages with ≥ 50 projects
├── analysis/                     # Statistical analysis & figure generation
│   ├── language_distribution.py  # Figure 1
│   ├── survival_analysis.py      # Figures 2–6 + results.md
│   ├── figures/                  # Generated PNGs
│   └── results.md                # Generated narrative results
├── data/                         # Intermediate + final CSVs
├── environment.yml               # Conda environment specification
├── requirements.txt              # pip alternative
├── data_filtering.md             # Detailed justification of every filter
└── readme.md                     # This file
```

Key source files:
[src/get_origins.py](src/get_origins.py),
[src/sample_origins.py](src/sample_origins.py),
[src/fetch_visits.py](src/fetch_visits.py),
[src/fetch_languages_graphql.py](src/fetch_languages_graphql.py),
[src/fetch_commits.py](src/fetch_commits.py),
[src/preprocess.py](src/preprocess.py),
[src/50_plus_filter.py](src/50_plus_filter.py),
[analysis/survival_analysis.py](analysis/survival_analysis.py),
[analysis/language_distribution.py](analysis/language_distribution.py).

---

## 2. Prerequisites

### 2.1 Software

| Requirement | Version |
|-------------|---------|
| Python      | 3.11    |
| Conda       | ≥ 23.x (Miniconda or Anaconda) — recommended |
| Git         | any recent |
| Disk space  | ≈ 5 GB free (the raw origin list alone is ≈ 1.6 GB) |
| OS          | Linux / macOS (Windows + WSL also fine) |

### 2.2 API credentials

| API | Required? | How to obtain | Where to pass it |
|-----|-----------|--------------|------------------|
| **Software Heritage** | Optional (but strongly recommended — un-authenticated is ~1 200 req/hr) | Create a free account at https://archive.softwareheritage.org/ → *Profile → Generate API Token* | `--token` flag on `fetch_visits.py`, or env var `SWH_API_TOKEN` |
| **GitHub** | **Required** for language + commit data | Create a personal access token (no scopes needed) at https://github.com/settings/tokens | `--github-token` flag, or env var `GITHUB_TOKEN` |

Never commit tokens. The repo's [.gitignore](.gitignore) already excludes `token.txt`.

---

## 3. Installation

### 3.1 Clone

```bash
git clone https://github.com/gjohns57/software_heritage_analysis.git
cd software_heritage_analysis
```

### 3.2 Create the Conda environment (recommended)

```bash
conda env create -f environment.yml
conda activate softwereproject
```

> Note: the environment name `softwereproject` is intentional and must match
> [environment.yml](environment.yml) — change both if you prefer a different name.

### 3.3 Or use pip + venv

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3.4 Verify

```bash
python -c "import pandas, lifelines, matplotlib, requests, httplink; print('OK')"
```

---

## 4. Reproduction Pipeline

All commands below assume you are in the **project root** (`software_heritage_analysis/`).
Every script is idempotent and resumable — they read existing output CSVs and skip already-processed records, so interruptions are safe.

The end-to-end pipeline produces the figures in [analysis/figures/](analysis/figures/) and the report in [analysis/results.md](analysis/results.md).

### Pipeline overview

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Step 0         │    │ Step 1         │    │ Step 2         │
│ get_origins.py │───▶│ sample_origins │───▶│ fetch_visits   │
│  (SWH /origins)│    │  (20 K GitHub) │    │  (SWH visits)  │
└────────────────┘    └────────────────┘    └───────┬────────┘
                                                    │
                              ┌─────────────────────┼─────────────────────┐
                              ▼                     ▼                     ▼
                       ┌────────────────┐  ┌─────────────────┐  ┌───────────────┐
                       │ Step 3         │  │ Step 4          │  │               │
                       │ fetch_languages│  │ fetch_commits   │  │  (merged)     │
                       │  (GH GraphQL)  │  │  (GH GraphQL)   │  │               │
                       └────────┬───────┘  └────────┬────────┘  └───────────────┘
                                └─────────┬────────┘
                                          ▼
                                ┌────────────────────┐
                                │ Step 5 preprocess  │
                                │  → analysis_dataset│
                                └─────────┬──────────┘
                                          ▼
                                ┌────────────────────┐
                                │ Step 6 50+ filter  │
                                │  → analysis_50plus │
                                └─────────┬──────────┘
                                          ▼
                                ┌────────────────────┐
                                │ analysis/*.py      │
                                │  figures + report  │
                                └────────────────────┘
```

---

### Step 0 — Collect Origins from Software Heritage

Paginates the SWH `/api/1/origins/` endpoint and records `(url, origin_visits_url)` for every project. Resumable via `Ctrl-C`; the pagination cursor is persisted in `data/origins.txt`.

```bash
python src/get_origins.py data/link_store.csv
```

| Field | Value |
|-------|-------|
| Output | [data/link_store.csv](data/link_store.csv) |
| Approx. row count | 10 715 000 |
| Approx. file size | 1.6 GB |
| Approx. runtime | Multiple days (un-authenticated). The original capture ran over ~4 days. |

> Skip-this-step shortcut: if you only want to reproduce the **analysis** (not the
> raw origin scrape), proceed directly to Step 1 using the committed
> [data/sampled_origins.csv](data/sampled_origins.csv) — it is the deterministic
> output of Step 1 given seed 42.

---

### Step 1 — Sample 20 000 GitHub Origins

Filters the full origin list to GitHub URLs only and draws a random sample of 20 000 using `random_state=42` (reproducible).

```bash
python src/sample_origins.py
```

| Field | Value |
|-------|-------|
| Reads | `data/link_store.csv` |
| Output | [data/sampled_origins.csv](data/sampled_origins.csv) |
| Rows | 20 000 |
| Runtime | ~1 min |

---

### Step 2 — Fetch Visit History from Software Heritage

For every sampled project, calls SWH to retrieve its full visit history (every archival event). This determines first-seen / last-active timestamps and snapshot counts.

```bash
# Un-authenticated (~1 200 req/hr — slow)
python src/fetch_visits.py

# Authenticated (recommended)
python src/fetch_visits.py --token "$SWH_API_TOKEN"
```

| Field | Value |
|-------|-------|
| Reads | `data/sampled_origins.csv` |
| Output | [data/visit_data.csv](data/visit_data.csv) |
| Runtime (auth) | ~6–8 hours |
| Runtime (un-auth) | ~18–24 hours |

The script flushes to disk every 50 records and resumes automatically on restart.

---

### Step 3 — Fetch Primary Language via GitHub GraphQL

Uses GitHub's GraphQL API to query 50 repositories per request, retrieving primary language plus a per-language byte breakdown.

```bash
python src/fetch_languages_graphql.py --github-token "$GITHUB_TOKEN"
```

| Field | Value |
|-------|-------|
| Reads | `data/sampled_origins.csv` |
| Output | [data/language_data.csv](data/language_data.csv) |
| Runtime | ~30 min (GraphQL 5 000 points/hr quota is sufficient) |

---

### Step 4 — Fetch Commit Counts via GitHub GraphQL

Queries the total commit count on each repository's default branch (batched 50 per request).

```bash
python src/fetch_commits.py --github-token "$GITHUB_TOKEN"
```

| Field | Value |
|-------|-------|
| Reads | `data/sampled_origins.csv` |
| Output | [data/commit_data.csv](data/commit_data.csv) |
| Runtime | ~25 min |

---

### Step 5 — Merge, Clean, and Engineer Features

Inner-joins visit + language + commit data on URL, drops projects missing a detected language or a successful snapshot, removes ambiguous (possibly private) repos, groups language variants (CoffeeScript→JavaScript, SCSS→CSS, …), computes lifespan metrics, and attaches per-language metadata (generation, memory-safety, paradigm, compiled/interpreted).

```bash
python src/preprocess.py
```

| Field | Value |
|-------|-------|
| Reads | `data/visit_data.csv`, `data/language_data.csv`, `data/commit_data.csv` |
| Output | [data/analysis_dataset.csv](data/analysis_dataset.csv) |
| Rows | 12 310 |
| Runtime | < 1 min |

See [data_filtering.md](data_filtering.md) for the full justification of every filter applied here.

---

### Step 6 — Restrict to Languages with ≥ 50 Projects

Removes the catch-all `"Other"` bucket and any language with fewer than 50 projects (insufficient statistical power for survival analysis).

```bash
python src/50_plus_filter.py
```

| Field | Value |
|-------|-------|
| Reads | `data/analysis_dataset.csv` |
| Output | [data/analysis_50plus.csv](data/analysis_50plus.csv) |
| Rows | 11 756 (across 22 languages) |
| Runtime | < 1 min |

---

## 5. Analysis & Figure Generation

### 5.1 Language distribution (Figure 1)

```bash
python analysis/language_distribution.py
```

Produces [analysis/figures/language_distribution.png](analysis/figures/language_distribution.png) — a horizontal bar chart of project counts per language.

### 5.2 Survival analysis (Figures 2–6 + report)

```bash
python analysis/survival_analysis.py
```

This single script performs:

- Kaplan–Meier estimation per language → `km_by_language.png`
- Kaplan–Meier estimation by language generation → `km_by_generation.png`
- Multivariate log-rank test (all 22 languages) + pairwise vs JavaScript
- Cox Proportional Hazards regression (generation, compiled, memory-safe, GC, log-commits) → `cox_hazard_ratios.png`
- Abandonment-rate ranking → `abandonment_by_language.png`
- Lifespan distribution boxplots → `lifespan_boxplot.png`
- A presentation-ready Markdown report at [analysis/results.md](analysis/results.md)

Total runtime: < 2 min.

---

## 6. Expected Final Outputs

After a full run, the following files are produced (and committed in the repo for reference):

```
data/
├── link_store.csv          (not committed — 1.6 GB)
├── sampled_origins.csv     20 000 rows
├── visit_data.csv          ≤ 20 000 rows
├── language_data.csv       ≤ 20 000 rows
├── commit_data.csv         ≤ 20 000 rows
├── analysis_dataset.csv    12 310 rows
└── analysis_50plus.csv     11 756 rows  ← final analysis dataset

analysis/figures/
├── language_distribution.png
├── km_by_language.png
├── km_by_generation.png
├── cox_hazard_ratios.png
├── abandonment_by_language.png
└── lifespan_boxplot.png

analysis/results.md         Narrative results, tables, & RQ answers
```

---

## 7. Headline Findings

(Full discussion in [analysis/results.md](analysis/results.md).)

- **Highest abandonment**: Ruby (59.3 %); **Lowest**: TypeScript (36.7 %) — a 22.5-point spread.
- **Median project survival**: ranges from 2.52 yr (TypeScript) to 5.47 yr (Dart).
- **Multivariate log-rank** across all 22 languages: χ² = 18.30, *p* = 0.630 → no statistically significant difference.
- **Cox regression**: none of {generation, compiled, memory-safe, garbage-collected, log-commits} reaches significance.
- **Take-away**: project-level factors (size, activity, community) likely matter more than language choice for predicting longevity.

---

## 8. Reproducibility Notes

- Random seed is fixed (`RANDOM_SEED = 42` in [src/sample_origins.py](src/sample_origins.py)). Running Step 1 on the same `link_store.csv` always yields the same 20 000-row sample.
- Steps 2–4 hit live external APIs. Repository counts may shift slightly over time as projects are deleted/privatised on GitHub. The committed CSVs reflect the state on **April 2025**.
- Steps 5–6 are deterministic functions of the input CSVs.
- The analysis scripts (Step 7) are deterministic given the input dataset.

If you re-run Steps 2–4 today, expect minor drift (a handful of additional 404s, a small handful of newly-detected languages). The downstream filters explicitly handle these cases — final dataset size should remain within ±1 % of 11 756.

---

## 11. License & Contact

Academic / educational use. Issues and pull requests are welcome via GitHub.
