"""
Plot the distribution of projects by primary programming language.

Usage:
    python analysis/language_distribution.py

Output:
    analysis/figures/language_distribution.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os

INPUT_FILE = "data/analysis_50plus.csv"
OUTPUT_DIR = "analysis/figures"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = pd.read_csv(INPUT_FILE)

    # Count projects per language
    lang_counts = df["primary_language"].value_counts()

    # Top 20 languages for the main plot
    top_20 = lang_counts.head(20)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(12, 7))

    colors = plt.cm.tab20(range(len(top_20)))
    bars = ax.barh(range(len(top_20)), top_20.values, color=colors)
    ax.set_yticks(range(len(top_20)))
    ax.set_yticklabels(top_20.index, fontsize=11)
    ax.invert_yaxis()  # Highest at top

    # Add count labels on bars
    for bar, count in zip(bars, top_20.values):
        pct = 100 * count / len(df)
        ax.text(bar.get_width() + 30, bar.get_y() + bar.get_height() / 2,
                f"{count:,}  ({pct:.1f}%)",
                va="center", fontsize=10)

    ax.set_xlabel("Number of Projects", fontsize=12)
    ax.set_title(f"Distribution of Projects by Primary Language (n={len(df):,})", fontsize=14, fontweight="bold")
    ax.set_xlim(0, top_20.values[0] * 1.25)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

    # Add a note for remaining languages
    remaining = len(lang_counts) - 20
    remaining_count = lang_counts.iloc[20:].sum()
    if remaining > 0:
        ax.text(0.98, 0.02, f"+ {remaining} other languages ({remaining_count:,} projects)",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=9, fontstyle="italic", color="gray")

    plt.tight_layout()

    output_path = os.path.join(OUTPUT_DIR, "language_distribution.png")
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    print(f"Saved to {output_path}")

    # Print table too
    print(f"\nAll languages ({len(lang_counts)} total):")
    for lang, count in lang_counts.items():
        pct = 100 * count / len(df)
        print(f"  {lang:25s} {count:6,}  ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
