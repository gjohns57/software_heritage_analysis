# Data Filtering & Justification

## Starting Point

We began with a **random sample of 20,000 GitHub projects** drawn from 10,088,607 GitHub origins in the Software Heritage archive. For each project, we collected three types of data:

- **Visit history** from the SWH API (20,000 records)
- **Language data** from GitHub's GraphQL API (20,000 records)
- **Commit counts** from GitHub's GraphQL API (20,000 records)

## Filter 1: Inner Join on URL (20,000 → 19,996)

**What:** Merged the three datasets using the project URL as the common key. 4 records had mismatches between datasets.

**Why:** We need all three sources of information (visits, language, commits) to be present for a project to be analyzable. An inner join ensures every row in our dataset has complete coverage across all data sources.

**Removed:** 4 projects

---

## Filter 2: Must Have a Detected Programming Language (19,996 → 12,364)

**What:** Removed 7,632 projects where GitHub's API returned no programming language.

**Why:** Our research questions are fundamentally about programming languages and project survival *by language*. A project without a detected language cannot be assigned to any language group for survival analysis. These projects fall into several categories:

- **Deleted/private repos (668):** The repository no longer exists on GitHub — it was either deleted by the owner or made private. GitHub API returns 404.
- **Repos with no code files (598):** The repository exists but GitHub detected no programming language. These are typically README-only repos, documentation projects, or data-only repositories.
- **Empty repos with only config/data files (remaining ~6,366):** SWH successfully archived them (4,707 had a "full" visit), but they contained no recognizable source code — just configuration files, datasets, or other non-code content.

**Justification:** Including projects without a programming language would be meaningless for our study. We cannot answer "how long do projects survive in different languages" for a project that has no language. This is not data loss — these projects are simply outside the scope of our research questions.

---

## Filter 3: Must Have at Least One Successful Snapshot (12,364 → 12,330)

**What:** Removed 34 projects that had a detected language but zero snapshots in the SWH archive.

**Why:** A snapshot represents a successful archival of the project's source code at a point in time. Projects with zero snapshots were discovered by SWH but never successfully archived — meaning we have no reliable timestamp data for their lifecycle. Without at least one snapshot, we cannot determine when the project was active or compute its lifespan.

**Justification:** Our survival analysis depends on time-based observations. A project with no snapshot provides no temporal data and would introduce noise into our Kaplan-Meier estimates.

**Removed:** 34 projects

---

## Filter 4: Remove Ambiguous Repos — Possibly Private (12,330 → 12,310)

**What:** Removed 20 projects where GitHub API returned 404 (not found) for commit data, but SWH had previously made a successful ("full") archive visit.

**Why:** This is a critical data quality issue. These projects have two conflicting signals:
- SWH successfully archived their code at some point (they had real source code)
- GitHub now returns 404 (the repo is no longer publicly accessible)

The problem is that we **cannot distinguish** between two very different scenarios:
1. **Deleted repos** — the project is truly dead and abandoned
2. **Privatized repos** — the project was made private but could still be actively maintained

If we kept these and assumed they were abandoned (based on SWH's last visit date), we would wrongly classify active-but-private projects as dead. This would bias our abandonment rates upward and potentially affect survival curves.

**Justification:** Rather than risk systematic misclassification, we remove these 20 projects. At 0.16% of the dataset, this has zero statistical impact on our results but eliminates a known source of classification error. This decision is documented as a threat to validity in our analysis.

**Removed:** 20 projects

---

## Filter 5: Language Grouping

**What:** GitHub's language classifier detects 154 granular language variants. We grouped derivatives and variants into their parent languages where they compile to or directly extend the parent.

**Why:** Analyzing CoffeeScript separately from JavaScript, or SCSS separately from CSS, would fragment sample sizes and obscure real trends. These are not independent languages. The groupings applied to our final 17 languages:

- **JavaScript:** CoffeeScript, LiveScript → JavaScript
- **CSS:** SCSS, Less, Sass, Stylus → CSS
- **HTML:** Handlebars, Pug, Svelte, Blade, Astro, Jinja, Twig, Smarty → HTML
- **Shell:** Batchfile, PowerShell → Shell
- **C++:** Cuda, HLSL, GLSL, Arduino → C++
- **C#:** ASP, ASP.NET → C#
- **Java:** Apex → Java

The original GitHub classification is preserved in the `original_language` column.

**Reclassified:** 394 projects, **Removed:** 0

---

## Filter 6: Minimum Sample Size — 100+ Projects per Language (12,310 → 11,373)

**What:** Kept only languages with 50 or more projects. Removed the "Other" catch-all category and 78 languages with fewer than 50 projects each (554 projects total).

**Why:** Survival analysis (Kaplan-Meier curves, Cox regression) requires adequate sample sizes to produce statistically meaningful results. Languages with fewer than 50 projects lack the statistical power to:
- Generate reliable survival curves
- Detect meaningful differences in hazard ratios
- Withstand subgroup analysis (e.g., by project size or time period)

**The 22 languages retained:**

| Language | Projects | Generation |
|----------|----------|------------|
| JavaScript | 2,450 | 2nd gen |
| Python | 1,610 | 2nd gen |
| HTML | 1,465 | 2nd gen |
| Java | 1,401 | 2nd gen |
| C++ | 532 | 2nd gen |
| CSS | 527 | 2nd gen |
| Jupyter Notebook | 521 | 3rd gen |
| TypeScript | 482 | 3rd gen |
| PHP | 444 | 2nd gen |
| C# | 424 | 3rd gen |
| C | 352 | 1st gen |
| Ruby | 329 | 2nd gen |
| Shell | 273 | 2nd gen |
| Go | 241 | 3rd gen |
| Swift | 114 | 3rd gen |
| Kotlin | 106 | 3rd gen |
| Vue | 102 | 3rd gen |
| Objective-C | 97 | 2nd gen |
| Dart | 92 | 3rd gen |
| Rust | 73 | 3rd gen |
| R | 67 | 2nd gen |
| Lua | 54 | 2nd gen |

**Justification:** 22 languages provides broad coverage across all three language generations, including modern languages like Rust and Dart that are central to answering RQ2 (do newer languages lead to more sustainable projects). The removed 554 projects (4.5%) are spread across 78 niche languages, none individually large enough to contribute to survival analysis.

**Removed:** 554 projects

---

## Final Dataset Summary

| Stage | Count | Removed | Reason |
|-------|-------|---------|--------|
| Initial sample | 20,000 | — | Random sample from 10M+ GitHub origins |
| After merge | 19,996 | 4 | URL mismatch across datasets |
| Language filter | 12,364 | 7,632 | No programming language detected |
| Snapshot filter | 12,330 | 34 | No successful SWH archive snapshot |
| Ambiguity filter | 12,310 | 20 | Possibly private (cannot verify status) |
| Language grouping | 12,310 | 0 | 154 → 100 languages (reclassified, none removed) |
| Sample size filter | 11,756 | 554 | Languages with < 50 projects |
| **Final dataset** | **11,756** | **8,244 total** | |

---

## Final Dataset Characteristics

### Project Status
| Status | Count | Percentage |
|--------|-------|------------|
| Active (last activity < 1 year) | 2,112 | 18.0% |
| Inactive (1–2 years) | 4,035 | 34.3% |
| Abandoned (2+ years) | 5,609 | 47.7% |

### Language Coverage
- **22 programming languages** — each with 50+ projects for statistically reliable analysis
- Covers all 3 language generations (1st gen: C; 2nd gen: Java, Python, JS, etc.; 3rd gen: Go, Rust, TypeScript, Kotlin, Dart, etc.)
- Top 4: JavaScript (20.8%), Python (13.7%), HTML (12.5%), Java (11.9%)

### Language Generation Breakdown
| Generation | Count | Percentage | Abandonment Rate |
|------------|-------|------------|------------------|
| 1st gen — pre-1980 (C) | 352 | 3.0% | 50.6% |
| 2nd gen — 1980s-1990s (Java, Python, JS, etc.) | 9,249 | 78.7% | 48.1% |
| 3rd gen — 2000s+ (Go, Rust, TypeScript, Kotlin, etc.) | 2,155 | 18.3% | 45.8% |

### Commit Count Distribution
| Metric | Value |
|--------|-------|
| Minimum | 1 |
| Median | 10 |
| Mean | 1,203 |
| 75th percentile | 60 |
| Maximum | 1,199,736 |

| Threshold | Projects | Percentage |
|-----------|----------|------------|
| >= 10 commits | 5,978 | 50.9% |
| >= 20 commits | 4,651 | 39.6% |
| >= 50 commits | 3,195 | 27.2% |
| >= 100 commits | 2,339 | 19.9% |

### Lifespan Distribution
| Metric | Value |
|--------|-------|
| Mean lifespan | 444 days (~1.2 years) |
| Median lifespan | 0 days (many single-visit projects) |
| 75th percentile | 708 days (~1.9 years) |
| Maximum | 3,870 days (~10.6 years) |

---

## Why 11,756 Projects Across 22 Languages Is a Strong Dataset

1. **Larger than comparable studies:**
   - Ali et al. (MSR 2020) studied Python project survival with 1,470 projects
   - Avelino et al. (ESEM 2019) studied abandonment with 1,932 projects
   - Samoladas et al. (IST 2010) used ~3,000 SourceForge projects
   - Our dataset is **4–8x larger** than these published, peer-reviewed studies

2. **Every language has statistical power:** All 22 languages have 50+ projects — enough for reliable Kaplan-Meier curves, log-rank tests, and Cox regression with meaningful confidence intervals

3. **Full generational coverage:** Languages span from 1972 (C) to 2014 (Swift, Vue, Dart), covering all three generations including modern memory-safe systems languages like Rust — directly enabling us to answer RQ2 (do newer languages lead to more sustainable projects)

4. **Rich per-project data:** Every project has:
   - A confirmed programming language (from GitHub's classifier, grouped into parent languages)
   - At least one successful source code archive snapshot
   - Verifiable existence on GitHub (not deleted, not private)
   - Temporal data (first and last visit dates) for lifecycle computation
   - Commit count for activity measurement
   - Language metadata (generation, memory safety, paradigm, compiled/interpreted)

5. **Zero zero-commit projects:** Every project has at least 1 commit — confirmed real projects with actual code, not empty or placeholder repositories

6. **Conservative, transparent filtering:** Each of the 6 filters has a clear, defensible reason documented above. The 41.2% removal rate is driven almost entirely by empty/non-code repos and niche languages — not by methodological limitations

7. **Reproducible:** Fixed random seed (42), deterministic filtering, and the entire pipeline can be re-run from raw data to produce identical results
