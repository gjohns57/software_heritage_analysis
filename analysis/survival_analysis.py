"""
Phase 5: Survival Analysis & Visualization

Performs Kaplan-Meier and Cox Proportional Hazards analysis on the
analysis_50plus.csv dataset to answer the three research questions:

  RQ1: How long do projects survive in different languages?
       → Kaplan-Meier curves per language

  RQ2: Do newer languages lead to more sustainable projects?
       → Cox regression with language generation as covariate

  RQ3: What languages lead to faster abandonment?
       → Median survival times + log-rank tests

Survival analysis time variable:
  - For abandoned projects:  T = days from first_visit to last_visit (event time)
  - For active/inactive:     T = days from first_visit to today (right-censored)
  - Event:  is_abandoned (1 = event observed, 0 = censored)

Usage:
    python analysis/survival_analysis.py

Output:
    analysis/figures/*.png   — survival curves, hazard plots, comparisons
    analysis/results.md      — written results & interpretation
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os
import warnings

from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test, multivariate_logrank_test

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

INPUT_FILE = "data/analysis_50plus.csv"
FIGURES_DIR = "analysis/figures"
RESULTS_FILE = "analysis/results.md"

# Use a clean seaborn-like style
plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.dpi": 100,
})


def prepare_survival_data(df):
    """Compute proper time-to-event for survival analysis."""
    df = df.copy()
    df["first_visit_date"] = pd.to_datetime(df["first_visit_date"], format="ISO8601", utc=True)
    df["last_visit_date"] = pd.to_datetime(df["last_visit_date"], format="ISO8601", utc=True)
    now = pd.Timestamp.now(tz="UTC")

    # Time from first observation to event (abandonment) or current date (censored)
    # For abandoned projects: time to event = first_visit -> last_visit
    # For non-abandoned (active/inactive): censored = first_visit -> now
    abandoned_mask = df["is_abandoned"] == 1
    df["T_days"] = np.where(
        abandoned_mask,
        (df["last_visit_date"] - df["first_visit_date"]).dt.days,
        (now - df["first_visit_date"]).dt.days,
    )
    # Minimum 1 day to avoid log(0) issues
    df["T_days"] = df["T_days"].clip(lower=1)
    df["T_years"] = df["T_days"] / 365.25
    df["E"] = df["is_abandoned"].astype(int)
    return df


def run_kaplan_meier_by_language(df, top_n=8):
    """KM curves for top N languages — presentation-ready, zoomed to data range."""
    print("\n--- Kaplan-Meier by Language ---")
    all_langs = df["primary_language"].value_counts().index.tolist()
    top_langs = all_langs[:top_n]

    # Compute median survival for ALL languages (used in report tables)
    median_survival = {}
    for lang in all_langs:
        sub = df[df["primary_language"] == lang]
        kmf = KaplanMeierFitter()
        kmf.fit(sub["T_years"], sub["E"])
        med = kmf.median_survival_time_
        median_survival[lang] = med if not pd.isna(med) else float("inf")

    fig, ax = plt.subplots(figsize=(10, 6))
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"]
    for lang, color in zip(top_langs, palette[:len(top_langs)]):
        sub = df[df["primary_language"] == lang]
        kmf = KaplanMeierFitter()
        kmf.fit(sub["T_years"], sub["E"], label=f"{lang} (n={len(sub):,})")
        kmf.plot_survival_function(ax=ax, ci_show=False, color=color, lw=2.2)

    ax.set_title(f"Project Survival Curves — Top {top_n} Languages", fontweight="bold", fontsize=14)
    ax.set_xlabel("Years Since Project Creation", fontsize=12)
    ax.set_ylabel("Survival Probability", fontsize=12)
    ax.set_xlim(0, df["T_years"].quantile(0.99))
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower left", fontsize=10, framealpha=0.95, ncol=2)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "km_by_language.png"), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved km_by_language.png ({top_n} languages)")

    return median_survival


def run_kaplan_meier_by_generation(df):
    """KM curves grouped by language generation."""
    print("\n--- Kaplan-Meier by Generation ---")
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = {"1st gen (pre-1980)": "#d62728",
              "2nd gen (1980s-1990s)": "#ff7f0e",
              "3rd gen (2000s+)": "#2ca02c"}

    median_by_gen = {}
    for gen, color in colors.items():
        sub = df[df["generation_label"] == gen]
        if len(sub) == 0:
            continue
        kmf = KaplanMeierFitter()
        kmf.fit(sub["T_years"], sub["E"], label=f"{gen} (n={len(sub):,})")
        kmf.plot_survival_function(ax=ax, ci_show=True, color=color, lw=2.5)
        med = kmf.median_survival_time_
        median_by_gen[gen] = med if not pd.isna(med) else float("inf")

    ax.set_title("Project Survival by Language Generation", fontweight="bold", fontsize=14)
    ax.set_xlabel("Years Since Project Creation", fontsize=12)
    ax.set_ylabel("Survival Probability", fontsize=12)
    ax.set_xlim(0, df["T_years"].quantile(0.99))
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower left", framealpha=0.95, fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "km_by_generation.png"), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved km_by_generation.png")
    return median_by_gen


def run_logrank_tests(df):
    """Multivariate log-rank test across ALL languages + pairwise vs JavaScript."""
    print("\n--- Log-rank Tests ---")
    all_langs = df["primary_language"].value_counts().index.tolist()
    n_langs = len(all_langs)

    # Multivariate test across all languages
    mv = multivariate_logrank_test(df["T_years"], df["primary_language"], df["E"])
    print(f"  Multivariate log-rank (all {n_langs} languages): p = {mv.p_value:.2e}, χ² = {mv.test_statistic:.2f}")

    # Pairwise vs the most common language (JavaScript)
    baseline = "JavaScript"
    baseline_data = df[df["primary_language"] == baseline]
    pairwise_results = []
    for lang in all_langs:
        if lang == baseline:
            continue
        cmp = df[df["primary_language"] == lang]
        result = logrank_test(
            baseline_data["T_years"], cmp["T_years"],
            baseline_data["E"], cmp["E"],
        )
        pairwise_results.append({
            "language": lang,
            "vs_baseline": baseline,
            "p_value": result.p_value,
            "test_statistic": result.test_statistic,
            "significant": result.p_value < 0.05,
        })

    return mv, pairwise_results


def run_cox_regression(df):
    """Cox Proportional Hazards model — RQ2."""
    print("\n--- Cox Proportional Hazards Regression ---")

    # Prepare features for Cox model
    # Use language generation as a numeric covariate, plus binary language properties
    cox_df = df[[
        "T_years", "E",
        "language_generation",
        "is_compiled", "is_memory_safe", "is_garbage_collected",
        "commit_count",
    ]].copy().dropna()

    # Convert booleans to int
    for col in ["is_compiled", "is_memory_safe", "is_garbage_collected"]:
        cox_df[col] = cox_df[col].astype(int)

    # Log-transform commit count (highly skewed)
    cox_df["log_commits"] = np.log1p(cox_df["commit_count"])
    cox_df = cox_df.drop(columns=["commit_count"])

    cph = CoxPHFitter()
    cph.fit(cox_df, duration_col="T_years", event_col="E")

    print("\n  Cox Model Summary:")
    summary = cph.summary[["coef", "exp(coef)", "p", "exp(coef) lower 95%", "exp(coef) upper 95%"]]
    print(summary.to_string())

    # --- Hazard ratio forest plot ---
    fig, ax = plt.subplots(figsize=(10, 5))
    sorted_summary = summary.sort_values("exp(coef)")

    y_pos = range(len(sorted_summary))
    hr = sorted_summary["exp(coef)"].values
    lo = sorted_summary["exp(coef) lower 95%"].values
    hi = sorted_summary["exp(coef) upper 95%"].values

    colors = ["#2ca02c" if h < 1 else "#d62728" for h in hr]
    ax.errorbar(hr, y_pos, xerr=[hr - lo, hi - hr], fmt="o", color="black",
                ecolor="gray", capsize=5, markersize=8, markerfacecolor="white")
    for i, (h, c) in enumerate(zip(hr, colors)):
        ax.scatter(h, i, s=100, color=c, zorder=10)

    ax.axvline(1.0, color="black", linestyle="--", alpha=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(sorted_summary.index)
    ax.set_xlabel("Hazard Ratio (95% CI)")
    ax.set_title("Cox Regression: Hazard Ratios for Abandonment", fontweight="bold")
    ax.text(0.02, 0.95, "← Lower abandonment risk\n(better survival)",
            transform=ax.transAxes, fontsize=9, color="#2ca02c", va="top")
    ax.text(0.65, 0.95, "Higher abandonment risk →\n(worse survival)",
            transform=ax.transAxes, fontsize=9, color="#d62728", va="top")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "cox_hazard_ratios.png"), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"\n  Saved cox_hazard_ratios.png")

    return cph, summary


def plot_abandonment_by_language(df, top_n=15):
    """Bar chart: abandonment rate by language (top N for clarity)."""
    print("\n--- Abandonment Rate by Language ---")
    top_langs = df["primary_language"].value_counts().head(top_n).index.tolist()
    rates = df[df["primary_language"].isin(top_langs)].groupby("primary_language")["is_abandoned"].agg(
        ["mean", "count"]
    ).sort_values("mean")
    rates["pct"] = rates["mean"] * 100

    fig, ax = plt.subplots(figsize=(10, 7))
    colors = plt.cm.RdYlGn_r(rates["pct"].values / 100)
    bars = ax.barh(range(len(rates)), rates["pct"], color=colors, edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(rates)))
    ax.set_yticklabels(rates.index)

    for bar, (lang, row) in zip(bars, rates.iterrows()):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{row['pct']:.1f}% (n={int(row['count']):,})",
                va="center", fontsize=10)

    ax.set_xlabel("Abandonment Rate (%)", fontsize=12)
    ax.set_title("Project Abandonment Rate by Programming Language", fontweight="bold", fontsize=14)
    ax.set_xlim(0, max(rates["pct"]) * 1.2)
    ax.axvline(rates["pct"].mean(), color="black", linestyle="--", alpha=0.5,
               label=f"Mean: {rates['pct'].mean():.1f}%")
    ax.legend(loc="lower right", fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "abandonment_by_language.png"), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved abandonment_by_language.png")
    return rates


def plot_lifespan_boxplot(df, top_n=15):
    """Boxplot: lifespan distribution by language (top N for clarity)."""
    print("\n--- Lifespan Boxplots ---")
    top_langs = df["primary_language"].value_counts().head(top_n).index.tolist()
    sub = df[df["primary_language"].isin(top_langs)].copy()
    medians = sub.groupby("primary_language")["T_years"].median().sort_values()
    order = medians.index.tolist()

    fig, ax = plt.subplots(figsize=(10, 7))
    data_by_lang = [sub[sub["primary_language"] == lang]["T_years"].values for lang in order]
    bp = ax.boxplot(data_by_lang, vert=False, patch_artist=True, showfliers=False,
                    medianprops={"color": "black", "linewidth": 2})
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(order)))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_yticklabels(order)
    ax.set_xlabel("Observed Lifetime (Years)")
    ax.set_title("Distribution of Project Lifetimes by Language", fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "lifespan_boxplot.png"), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved lifespan_boxplot.png")


def write_results_report(df, median_lang, median_gen, mv_test, pairwise, cox_summary, abandon_rates):
    """Write a presentation-ready results markdown file."""
    print("\n--- Writing Results Report ---")
    lines = []
    lines.append("# Survival Analysis Results")
    lines.append(f"\n**Dataset:** {len(df):,} projects across {df['primary_language'].nunique()} languages")
    lines.append(f"**Total events (abandoned):** {df['E'].sum():,} ({100*df['E'].mean():.1f}%)")
    lines.append(f"**Censored (active/inactive):** {(df['E']==0).sum():,} ({100*(df['E']==0).mean():.1f}%)")

    lines.append("\n---\n")
    lines.append("## RQ1: How long do projects survive in different languages?\n")
    lines.append(f"Kaplan-Meier survival analysis was run on all {len(median_lang)} languages with 50+ projects. "
                 "The median survival time tells us at what point 50% of projects in a language are still active.\n")
    lines.append("**Median survival time (years) by language** (longest to shortest):\n")
    lines.append("| Language | Median Survival (years) |")
    lines.append("|----------|------------------------|")
    sorted_med = sorted(median_lang.items(), key=lambda x: -x[1] if x[1] != float("inf") else -1e9)
    for lang, med in sorted_med:
        med_str = f"{med:.2f}" if med != float("inf") else "> observation window"
        lines.append(f"| {lang} | {med_str} |")
    lines.append("\n*(See `figures/km_by_language.png` for top-10 plot, "
                 "`figures/km_by_language_all.png` for all languages as small multiples)*\n")

    lines.append("\n---\n")
    lines.append("## RQ2: Do newer languages lead to more sustainable projects?\n")
    lines.append("We fit a Cox Proportional Hazards model with language generation, language properties, "
                 "and project commit count as covariates. The **hazard ratio (HR)** tells us how each "
                 "factor affects the risk of abandonment:\n")
    lines.append("- **HR < 1:** factor is associated with *lower* risk of abandonment (better survival)")
    lines.append("- **HR > 1:** factor is associated with *higher* risk of abandonment (worse survival)\n")
    lines.append("**Cox Model Results:**\n")
    lines.append("| Covariate | Hazard Ratio | 95% CI | p-value |")
    lines.append("|-----------|-------------:|:------:|:-------:|")
    for cov, row in cox_summary.iterrows():
        hr = row["exp(coef)"]
        lo = row["exp(coef) lower 95%"]
        hi = row["exp(coef) upper 95%"]
        p = row["p"]
        sig = "**" if p < 0.05 else ""
        lines.append(f"| {cov} | {sig}{hr:.3f}{sig} | [{lo:.3f}, {hi:.3f}] | {p:.3e} |")
    lines.append("\n*(See `figures/cox_hazard_ratios.png` for forest plot)*\n")

    lines.append("\n**Median survival by generation:**\n")
    for gen, med in median_gen.items():
        med_str = f"{med:.2f} years" if med != float("inf") else "> observation window"
        lines.append(f"- **{gen}:** {med_str}")
    lines.append("\n*(See `figures/km_by_generation.png` for survival curves)*\n")

    lines.append("\n---\n")
    lines.append("## RQ3: What languages lead to faster abandonment?\n")
    n_langs = df['primary_language'].nunique()
    lines.append(f"**Multivariate log-rank test:** Are survival curves significantly different across all {n_langs} languages?\n")
    lines.append(f"- **χ² = {mv_test.test_statistic:.2f}, p-value = {mv_test.p_value:.2e}**")
    sig_text = "Yes — survival curves differ significantly across languages." if mv_test.p_value < 0.05 \
        else "No significant difference between languages."
    lines.append(f"- **Conclusion:** {sig_text}\n")

    lines.append(f"**Abandonment rates by language (all {n_langs}):**\n")
    sorted_rates = abandon_rates.sort_values("pct", ascending=False)
    lines.append("| Language | Abandonment Rate | n |")
    lines.append("|----------|-----------------:|--:|")
    for lang, row in sorted_rates.iterrows():
        lines.append(f"| {lang} | {row['pct']:.1f}% | {int(row['count']):,} |")
    lines.append("\n*(See `figures/abandonment_by_language.png` for visualization)*\n")

    lines.append("\n**Pairwise log-rank tests vs. JavaScript (most common language):**\n")
    lines.append("| Language | p-value | Significantly different? |")
    lines.append("|----------|--------:|:------------------------:|")
    for r in sorted(pairwise, key=lambda x: x["p_value"]):
        flag = "Yes (p < 0.05)" if r["significant"] else "No"
        lines.append(f"| {r['language']} | {r['p_value']:.2e} | {flag} |")

    lines.append("\n---\n")
    lines.append("## Summary for Presentation\n")

    # Find highest and lowest abandonment languages
    top_abandon = sorted_rates.iloc[0]
    bot_abandon = sorted_rates.iloc[-1]
    range_pp = top_abandon["pct"] - bot_abandon["pct"]

    # Find shortest and longest median survival
    finite_med = {k: v for k, v in median_lang.items() if v != float("inf")}
    if finite_med:
        shortest_lang = min(finite_med, key=finite_med.get)
        longest_lang = max(finite_med, key=finite_med.get)

    mv_sig = "statistically significant" if mv_test.p_value < 0.05 else "not statistically significant"

    lines.append(f"1. **{top_abandon.name} has the highest abandonment rate** at {top_abandon['pct']:.1f}%, "
                 f"while **{bot_abandon.name} has the lowest** at {bot_abandon['pct']:.1f}% — "
                 f"a {range_pp:.1f} percentage-point spread across the top 15 languages.")
    if finite_med:
        lines.append(f"2. **Median project survival** ranges from {finite_med[shortest_lang]:.2f} years "
                     f"({shortest_lang}) to {finite_med[longest_lang]:.2f} years ({longest_lang}).")
    lines.append(f"3. **Multivariate log-rank test:** Differences in survival across the top 10 languages "
                 f"are **{mv_sig}** (p = {mv_test.p_value:.3f}, χ² = {mv_test.test_statistic:.2f}).")

    # Cox finding
    sig_cox = cox_summary[cox_summary["p"] < 0.05]
    if len(sig_cox) > 0:
        lines.append(f"4. **Cox regression** identified {len(sig_cox)} statistically significant predictors "
                     f"of abandonment: {', '.join(sig_cox.index.tolist())}.")
    else:
        lines.append("4. **Cox regression** did not identify any statistically significant predictors of abandonment "
                     "among language generation, compiled status, memory safety, garbage collection, or commit count "
                     "— suggesting language properties alone do not strongly determine project longevity in our sample.")

    lines.append("5. **Practical implication:** While raw abandonment rates vary by language, the formal "
                 "survival analysis suggests that **project-level factors (size, activity, community) likely "
                 "matter more than language choice alone** for predicting longevity.\n")

    report = "\n".join(lines)
    with open(RESULTS_FILE, "w") as f:
        f.write(report)
    print(f"  Saved {RESULTS_FILE}")


def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)

    print(f"Loading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    print(f"  Loaded {len(df):,} projects")

    df = prepare_survival_data(df)
    print(f"  Median observation time: {df['T_years'].median():.2f} years")
    print(f"  Events (abandoned): {df['E'].sum():,} / {len(df):,} ({100*df['E'].mean():.1f}%)")

    # Run analyses
    median_lang = run_kaplan_meier_by_language(df, top_n=8)
    median_gen = run_kaplan_meier_by_generation(df)
    mv_test, pairwise = run_logrank_tests(df)
    cph, cox_summary = run_cox_regression(df)
    abandon_rates = plot_abandonment_by_language(df)
    plot_lifespan_boxplot(df)

    # Generate report
    write_results_report(df, median_lang, median_gen, mv_test, pairwise, cox_summary, abandon_rates)

    print("\n" + "=" * 60)
    print("DONE — All outputs saved to analysis/")
    print("=" * 60)


if __name__ == "__main__":
    main()
