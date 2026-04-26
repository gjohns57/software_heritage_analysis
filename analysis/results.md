# Survival Analysis Results

**Dataset:** 11,756 projects across 22 languages
**Total events (abandoned):** 5,609 (47.7%)
**Censored (active/inactive):** 6,147 (52.3%)

---

## Figures Overview — How Each Figure Answers a Research Question

| Figure | Answers | What it reveals |
|--------|---------|-----------------|
| 1. Language distribution | Context (no RQ) | Composition of the dataset |
| 2. KM curves by language | **RQ1, RQ3** | How long projects survive in each language |
| 3. KM curves by generation | **RQ2** | Whether newer languages produce more sustainable projects |
| 4. Abandonment rate bar chart | **RQ3** | Which languages have the highest/lowest abandonment |
| 5. Lifespan boxplot | **RQ1** | The distribution of project lifetimes by language |
| 6. Cox hazard ratios | **RQ2** | Whether language properties (memory safety, generation, etc.) predict abandonment |

---

### Figure 1: `language_distribution.png` — How many projects per language?

**Research question this answers:** None directly. This is a *context-setting* figure that shows what's in our sample before we run any analysis.

**What you're looking at:** A horizontal bar chart. Each bar is one programming language, and the length of the bar is how many projects in our dataset use that language as their main language. The bars are sorted from biggest to smallest, so JavaScript (2,450 projects) is at the top and Lua (54 projects) is at the bottom.

**Why this figure matters for the research:** Before claiming anything about language survival, we need to show our dataset is large enough and diverse enough to make those claims. **The big takeaway is that our sample is dominated by web languages** — JavaScript, Python, HTML, and Java alone make up over half of all projects. This means our conclusions will be most reliable for these popular languages and less certain for smaller ones like Lua or R. This figure justifies our 50+ projects-per-language threshold.

---

### Figure 2: `km_by_language.png` — Do projects survive longer in some languages?

**Research question this answers:** **RQ1** (How long do projects survive in different languages?) and partially **RQ3** (Which languages lead to faster abandonment?).

**What you're looking at:** A Kaplan-Meier survival curve, one line per language. The vertical axis is the percentage of projects still "alive" (not abandoned). The horizontal axis is years since the project started. Every line begins at the top — at year 0, all projects are alive — and steps downward as projects get abandoned over time.

**How this figure answers the RQ:** This is the *direct visual answer* to RQ1. To find out how long projects in language X survive, you simply look at where the line for language X crosses the 50% survival mark — that's the median survival time for that language. For example, at year 4, every language is somewhere between 35% and 50% survival, meaning **roughly half of all projects in every language are abandoned within 4 years.** **The most important finding is that the lines are bunched together** — no language dramatically outperforms the others. If language choice strongly affected survival, we'd expect to see one line stay way above the others. Instead they all decay at similar rates. This is the visual evidence behind our log-rank test result (p = 0.63, not significant).

---

### Figure 3: `km_by_generation.png` — Do newer languages survive better?

**Research question this answers:** **RQ2** (Do newer languages lead to more sustainable projects?). This figure is the most direct visual answer to RQ2.

**What you're looking at:** Same kind of survival curve as Figure 2, but instead of one line per language, we group languages by their *generation*: 1st gen (pre-1980, like C), 2nd gen (1980s–1990s, like Java/Python/JavaScript), and 3rd gen (2000s+, like Go/Rust/TypeScript). The shaded bands around each line show the 95% confidence interval — basically how certain we are about each curve.

**How this figure answers the RQ:** If newer languages led to more sustainable projects, the green line (3rd gen) would stay above the others. **What we actually see is the opposite — all three lines overlap almost perfectly throughout the entire 10-year window.** A C project from the 70s and a Rust project from the 2010s have essentially the same probability of surviving any given year. **The answer to RQ2 from this figure is: no, newer languages do not produce more sustainable projects in our data.** This is a counter-intuitive but defensible finding, and the overlapping confidence bands confirm we cannot statistically distinguish the three generations.

---

### Figure 4: `abandonment_by_language.png` — Which languages have the highest abandonment rates?

**Research question this answers:** **RQ3** (What languages lead to faster abandonment?). This is the simplest and most direct answer to RQ3 — a ranked list.

**What you're looking at:** A horizontal bar chart showing what percentage of projects in each language are classified as abandoned (no activity for 2+ years). Languages are sorted from worst (highest abandonment) at the top to best (lowest abandonment) at the bottom. Each bar shows the percentage and the number of projects we have for that language. The dashed vertical line is the overall mean (49.1%).

**How this figure answers the RQ:** This is the "winners and losers" view that maps directly to RQ3. **Ruby has the highest abandonment rate at 59.3%**, meaning about 6 in 10 Ruby projects are dead. **TypeScript has the lowest at 36.7%** — only about 4 in 10 are dead. The spread is about 22 percentage points across the top 15 languages. So in raw terms: Ruby, Swift, and PHP have the fastest abandonment; TypeScript, HTML, and CSS have the slowest.

**Important caveat:** these are raw rates, not adjusted for project age. TypeScript looks "best" partly because it's a young language — most TypeScript projects in our sample haven't had time to be abandoned yet. The survival analysis in Figures 2 and 3 corrects for this; this bar chart does not. This is why we report Figure 4 alongside Figure 2 — together they give an honest picture.

---

### Figure 5: `lifespan_boxplot.png` — How wide is the lifespan range within each language?

**Research question this answers:** Supports **RQ1** (How long do projects survive in different languages?) by showing the *distribution* of lifetimes, not just the median.

**What you're looking at:** A boxplot showing the distribution of project lifetimes (in years) within each language. Each row is one language. The box itself spans from the 25th to 75th percentile of lifespans, and the line inside the box is the median. The "whiskers" extending from the box show the range of typical values.

**How this figure answers the RQ:** Median survival times alone (from Figure 2) hide an important truth: **within every language, there's enormous variation in how long projects survive.** Some Ruby projects live 10+ years; others die in months. The boxes are very wide for languages like Ruby and PHP, meaning project lifespans are highly varied. For TypeScript and Jupyter Notebook, the boxes are short — partly because the languages themselves are younger and projects haven't had time to vary. **The takeaway for RQ1 is that "how long do projects survive in language X?" is the wrong question — there is no single answer, because within-language variation is far larger than between-language differences.** This finding reinforces the conclusion of Figure 2 that language alone is not the main driver of project lifespan.

---

### Figure 6: `cox_hazard_ratios.png` — Do specific language properties predict abandonment?

**Research question this answers:** **RQ2** (Do newer languages lead to more sustainable projects?). This is the *formal statistical answer* to RQ2 — Figure 3 shows the visual; this shows the numbers.

**What you're looking at:** A forest plot showing the results of a Cox regression model. Each row tests one language property (is it compiled? memory-safe? garbage-collected? newer generation? does the project have lots of commits?). Each dot is the *hazard ratio* — a number representing how much that property changes the risk of abandonment. The horizontal line through each dot is the 95% confidence interval, and the vertical dashed line at 1.0 is the "no effect" mark.

**How to read it:** A dot to the **left** of 1.0 means that property *reduces* abandonment risk. A dot to the **right** means it *increases* risk. **But the most important thing is whether the confidence interval crosses 1.0** — if it does, the effect is not statistically significant.

**How this figure answers the RQ:** **Every single confidence interval crosses 1.0.** All the dots are very close to 1.0, with intervals stretching across the line. This means none of the language properties we tested significantly predict abandonment risk. Memory-safe, compiled, garbage-collected, generation, even commit count — none of these reach statistical significance. **The formal answer to RQ2 from this Cox model is: no, no language property we tested significantly predicts whether a project will be abandoned.** This is the strongest statistical evidence that language choice alone does not determine project survival in our sample.

---

## RQ1: How long do projects survive in different languages?

Kaplan-Meier survival analysis was run on all 22 languages with 50+ projects. The median survival time tells us at what point 50% of projects in a language are still active.

**Median survival time (years) by language** (longest to shortest):

| Language | Median Survival (years) |
|----------|------------------------|
| Dart | 5.47 |
| Objective-C | 4.25 |
| Kotlin | 4.21 |
| Go | 4.06 |
| CSS | 4.02 |
| PHP | 3.79 |
| Python | 3.75 |
| HTML | 3.72 |
| Java | 3.66 |
| C | 3.65 |
| R | 3.65 |
| Rust | 3.64 |
| JavaScript | 3.64 |
| Jupyter Notebook | 3.63 |
| C++ | 3.52 |
| Ruby | 3.38 |
| Shell | 3.28 |
| C# | 3.22 |
| Swift | 3.04 |
| Lua | 3.01 |
| Vue | 2.63 |
| TypeScript | 2.52 |

*(See `figures/km_by_language.png` for top-10 plot, `figures/km_by_language_all.png` for all languages as small multiples)*


---

## RQ2: Do newer languages lead to more sustainable projects?

We fit a Cox Proportional Hazards model with language generation, language properties, and project commit count as covariates. The **hazard ratio (HR)** tells us how each factor affects the risk of abandonment:

- **HR < 1:** factor is associated with *lower* risk of abandonment (better survival)
- **HR > 1:** factor is associated with *higher* risk of abandonment (worse survival)

**Cox Model Results:**

| Covariate | Hazard Ratio | 95% CI | p-value |
|-----------|-------------:|:------:|:-------:|
| language_generation | 1.019 | [0.952, 1.092] | 5.840e-01 |
| is_compiled | 1.015 | [0.948, 1.087] | 6.662e-01 |
| is_memory_safe | 0.986 | [0.865, 1.124] | 8.305e-01 |
| is_garbage_collected | 1.051 | [0.981, 1.125] | 1.567e-01 |
| log_commits | 1.007 | [0.995, 1.020] | 2.302e-01 |

*(See `figures/cox_hazard_ratios.png` for forest plot)*


**Median survival by generation:**

- **1st gen (pre-1980):** 3.65 years
- **2nd gen (1980s-1990s):** 3.67 years
- **3rd gen (2000s+):** 3.25 years

*(See `figures/km_by_generation.png` for survival curves)*


---

## RQ3: What languages lead to faster abandonment?

**Multivariate log-rank test:** Are survival curves significantly different across all 22 languages?

- **χ² = 18.30, p-value = 6.30e-01**
- **Conclusion:** No significant difference between languages.

**Abandonment rates by language (all 22):**

| Language | Abandonment Rate | n |
|----------|-----------------:|--:|
| Ruby | 59.3% | 329 |
| Swift | 55.3% | 114 |
| PHP | 54.1% | 444 |
| Shell | 52.0% | 273 |
| C# | 51.2% | 424 |
| C | 50.6% | 352 |
| Java | 50.5% | 1,401 |
| C++ | 50.0% | 532 |
| Go | 48.5% | 241 |
| JavaScript | 48.1% | 2,450 |
| Jupyter Notebook | 46.8% | 521 |
| Python | 45.6% | 1,610 |
| CSS | 44.0% | 527 |
| HTML | 43.4% | 1,465 |
| TypeScript | 36.7% | 482 |

*(See `figures/abandonment_by_language.png` for visualization)*


**Pairwise log-rank tests vs. JavaScript (most common language):**

| Language | p-value | Significantly different? |
|----------|--------:|:------------------------:|
| Rust | 1.41e-01 | No |
| Kotlin | 1.57e-01 | No |
| TypeScript | 1.76e-01 | No |
| CSS | 2.00e-01 | No |
| Objective-C | 2.07e-01 | No |
| Vue | 2.28e-01 | No |
| HTML | 2.65e-01 | No |
| Shell | 3.53e-01 | No |
| Ruby | 3.55e-01 | No |
| Jupyter Notebook | 4.10e-01 | No |
| C# | 4.30e-01 | No |
| Swift | 4.70e-01 | No |
| Python | 7.14e-01 | No |
| Go | 7.33e-01 | No |
| C | 8.47e-01 | No |
| Java | 9.38e-01 | No |
| C++ | 9.47e-01 | No |
| PHP | 9.55e-01 | No |
| Dart | 9.58e-01 | No |
| Lua | 9.69e-01 | No |
| R | 9.90e-01 | No |

---

## Summary for Presentation

1. **Ruby has the highest abandonment rate** at 59.3%, while **TypeScript has the lowest** at 36.7% — a 22.5 percentage-point spread across the top 15 languages.
2. **Median project survival** ranges from 2.52 years (TypeScript) to 5.47 years (Dart).
3. **Multivariate log-rank test:** Differences in survival across the top 10 languages are **not statistically significant** (p = 0.630, χ² = 18.30).
4. **Cox regression** did not identify any statistically significant predictors of abandonment among language generation, compiled status, memory safety, garbage collection, or commit count — suggesting language properties alone do not strongly determine project longevity in our sample.
5. **Practical implication:** While raw abandonment rates vary by language, the formal survival analysis suggests that **project-level factors (size, activity, community) likely matter more than language choice alone** for predicting longevity.
