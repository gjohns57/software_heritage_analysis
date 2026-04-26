# Software Heritage Analysis — Project Plan (COSC 540)

## Research Questions
- **RQ1:** How long do projects survive in different languages?
- **RQ2:** Do newer languages lead to more sustainable projects?
- **RQ3:** What languages lead to faster abandonment?

---

## Phase 1: Data Collection from Software Heritage Archive ✅ COMPLETED

The Software Heritage archive contains over 430 million projects spanning five decades. To study project lifecycles at scale, we first needed to build a comprehensive list of origins (projects) from the archive. We developed a paginated crawler that iterates through the SWH API's origin listing endpoint, collecting project URLs and their corresponding visit endpoints.

This ran over multiple days, collecting **10.7 million origins** across platforms including GitHub (94%), GitLab, npm, Bitbucket, PyPI, and more — stored as a 1.6 GB dataset.

**Script:** `src/get_origins.py` → **Output:** `data/link_store.csv` (10,715,000 origins)

---

## Phase 2: Sampling & Environment Setup ✅ COMPLETED

Analyzing all 10.7 million origins is infeasible given API rate limits and project scope. Following standard empirical software engineering methodology, we drew a **random sample of 20,000 GitHub projects** — large enough for statistically significant survival analysis while remaining tractable for data collection.

We filtered to GitHub-only origins (10,088,607 projects) because GitHub provides structured language metadata through its API, enabling reliable language detection. A reproducible conda environment was created so all team members can run the pipeline identically.

**Script:** `src/sample_origins.py` → **Output:** `data/sampled_origins.csv` (20,000 projects)

---

## Phase 3: Collecting Project Metadata 

To answer our research questions, we need two pieces of information for each sampled project: **when was it active** (lifecycle data) and **what language is it written in**.

### 3a. Visit History Collection

The SWH archive tracks "visits" — periodic snapshots of each project over time. By collecting the full visit history for each project, we can determine when a project was first discovered, when it was last active, and how frequently it was updated. This directly enables us to classify projects as active, inactive, or abandoned.

**Script:** `src/fetch_visits.py` → **Output:** `data/visit_data.csv`

### 3b. Language Detection 

We detect each project's primary programming language using two complementary approaches: the **GitHub API** (provides byte counts per language — most accurate) and **SWH file extension analysis** as a fallback for projects where GitHub data is unavailable. This dual-source approach aligns with the methodology used by Desmazières et al. [6] in their MSR 2025 study.

**Script:** `src/fetch_languages.py` → **Output:** `data/language_data.csv`

---

## Phase 4: Data Processing & Feature Engineering 

Once all raw data is collected, we merge visit history and language data into a single analysis-ready dataset. This phase involves:

- **Cleaning:** Handle missing values (deleted/private repos, empty repos), remove non-code projects, standardize date formats
- **Project status classification:** Based on visit timestamps, each project is labeled as:
  - **Active** — last activity within 1 year
  - **Inactive** — no activity for 1–2 years
  - **Abandoned** — no activity for 2+ years
  - *(Thresholds from Khondhu et al. [8] and Avelino et al. [9])*
- **Feature computation:** Lifespan (days), primary language, language generation (1st/2nd/3rd gen), language properties (memory-safe, compiled, garbage-collected, paradigm), activity density (visits per year)

**Output:** `data/analysis_dataset.csv`

---

## Phase 5: Statistical Analysis & Visualization 

This is where we answer our research questions using survival analysis methods and produce publication-quality figures.

- **Kaplan-Meier survival curves** grouped by language → directly answers **RQ1** (how long do projects survive) and **RQ3** (which languages see faster abandonment)
- **Cox Proportional Hazards model** with language generation and properties as covariates → answers **RQ2** (do newer languages lead to more sustainable projects)
- **Log-rank tests** for statistical significance between language groups
- **Visualizations:** Survival curves, hazard ratio forest plots, language popularity timelines, lifespan boxplots, abandonment rate comparisons

**Tools:** Python `lifelines` library for survival analysis, `matplotlib`/`seaborn` for figures

---

## Progress Summary

| Phase | Status | What We Have |
|-------|--------|--------------|
| 1. Origin Collection | ✅ Done | 10.7M origins from SWH archive |
| 2. Sampling & Setup | ✅ Done | 20K projects sampled, environment ready |
| 3. Metadata Collection | 🔄 ~90% | Visit fetcher running, language script ready |
| 4. Processing & Features | ⬜ Next | ~1 week |
| 5. Analysis & Figures | ⬜ Final | ~1 week |

**Overall: ~60% complete — all data infrastructure built, collection nearly finished, two analysis phases remain**
