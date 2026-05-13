"""
Generate figures used in the written report:
  - pipeline_flow.png : conceptual end-to-end pipeline diagram
  - filter_funnel.png : six-stage filtering funnel from 20K to 11,756
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

FIGURES_DIR = "analysis/figures"
os.makedirs(FIGURES_DIR, exist_ok=True)


# ----------------------------- Figure 1: pipeline -----------------------------
def draw_box(ax, x, y, w, h, text, color, fontsize=10):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.08",
        facecolor=color, edgecolor="black", linewidth=1.5,
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center",
            fontsize=fontsize, fontweight="bold")


def draw_arrow(ax, x1, y1, x2, y2, style="->", lw=1.8):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle=style, lw=lw, color="black",
                        shrinkA=2, shrinkB=2),
    )


def build_pipeline():
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")

    SRC = "#FFE4B5"      # source (warm yellow)
    COLL = "#FFD58A"     # collection
    SAMP = "#90EE90"     # sampling (green)
    ENR = "#A8D8EA"      # enrichment (blue)
    PROC = "#FFB6C1"     # processing (pink)
    OUT = "#DDA0DD"      # analysis (purple)

    # Row 1: source / collection / sampling
    draw_box(ax, 0.3, 8.2, 3.2, 1.3,
             "Software Heritage\n/origins/ API\n(public archive)", SRC, 10)
    draw_box(ax, 5.4, 8.2, 3.2, 1.3,
             "Crawl all pages\n10.7M origins\n(1.6 GB CSV)", COLL, 10)
    draw_box(ax, 10.5, 8.2, 3.2, 1.3,
             "Filter to GitHub\nRandom sample\nn = 20,000", SAMP, 10)

    draw_arrow(ax, 3.5, 8.85, 5.4, 8.85)
    draw_arrow(ax, 8.6, 8.85, 10.5, 8.85)

    # Row 2: three enrichment branches
    draw_box(ax, 0.3, 5.6, 4.2, 1.4,
             "SWH Visit History\n(first / last visit,\nsnapshot counts)", ENR, 10)
    draw_box(ax, 4.9, 5.6, 4.2, 1.4,
             "GitHub GraphQL\nPrimary Language\n(batched, 50 repos / req)", ENR, 10)
    draw_box(ax, 9.5, 5.6, 4.2, 1.4,
             "GitHub GraphQL\nCommit Counts\n(batched, 50 repos / req)", ENR, 10)

    draw_arrow(ax, 12.1, 8.2, 2.4, 7.0)
    draw_arrow(ax, 12.1, 8.2, 7.0, 7.0)
    draw_arrow(ax, 12.1, 8.2, 11.6, 7.0)

    # Row 3: merge / clean
    draw_box(ax, 3.0, 3.4, 8.0, 1.2,
             "Inner join on URL + 6-stage filtering\n"
             "(language present, snapshot present, ambiguity removed,\n"
             "languages grouped, n >= 50 per language)", PROC, 10)

    draw_arrow(ax, 2.4, 5.6, 5.0, 4.6)
    draw_arrow(ax, 7.0, 5.6, 7.0, 4.6)
    draw_arrow(ax, 11.6, 5.6, 9.0, 4.6)

    # Row 3.5: cleaned dataset
    draw_box(ax, 4.5, 1.8, 5.0, 1.0,
             "Analysis-ready dataset\nn = 11,756 across 22 languages", PROC, 10)
    draw_arrow(ax, 7.0, 3.4, 7.0, 2.8)

    # Row 4: analyses
    draw_box(ax, 0.3, 0.1, 3.7, 1.2,
             "Kaplan-Meier\nsurvival curves\n(RQ1, RQ2)", OUT, 9.5)
    draw_box(ax, 5.1, 0.1, 3.7, 1.2,
             "Cox Proportional\nHazards Regression\n(RQ2)", OUT, 9.5)
    draw_box(ax, 9.9, 0.1, 3.7, 1.2,
             "Log-rank tests +\nabandonment ranking\n(RQ3)", OUT, 9.5)

    draw_arrow(ax, 7.0, 1.8, 2.2, 1.3)
    draw_arrow(ax, 7.0, 1.8, 7.0, 1.3)
    draw_arrow(ax, 7.0, 1.8, 11.8, 1.3)

    ax.set_title(
        "End-to-end pipeline: from the Software Heritage archive to survival analysis",
        fontsize=13, fontweight="bold", pad=12,
    )

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "pipeline_flow.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {out_path}")


# ----------------------------- Figure 2: filter funnel ------------------------
def build_funnel():
    stages = [
        ("Random sample (GitHub)",       20000),
        ("After inner join",             19996),
        ("Language detected",            12364),
        ("At least one snapshot",        12330),
        ("Non-ambiguous status",         12310),
        ("Language with n >= 50",        11756),
    ]
    labels = [s[0] for s in stages]
    counts = [s[1] for s in stages]
    max_count = counts[0]

    fig, ax = plt.subplots(figsize=(11, 7))
    y_positions = np.arange(len(stages))[::-1]
    colors = plt.cm.viridis(np.linspace(0.25, 0.85, len(stages)))

    for i, (label, count, color) in enumerate(zip(labels, counts, colors)):
        width = count / max_count
        left = (1 - width) / 2
        ax.barh(y_positions[i], width, left=left, height=0.72,
                color=color, edgecolor="black", linewidth=1.2)
        ax.text(0.5, y_positions[i],
                f"{label}\nn = {count:,}",
                ha="center", va="center",
                fontsize=11, fontweight="bold", color="white")

        if i > 0:
            removed = counts[i - 1] - count
            if removed > 0:
                pct = 100 * removed / counts[i - 1]
                ax.text(1.04, (y_positions[i] + y_positions[i - 1]) / 2,
                        f"removed: {removed:,}  ({pct:.1f}%)",
                        va="center", fontsize=10, color="#b22222",
                        fontweight="bold")

    ax.set_xlim(-0.02, 1.35)
    ax.set_ylim(-0.6, len(stages) - 0.3)
    ax.axis("off")
    ax.set_title(
        "Filtering funnel: from the initial random sample to the final analysis dataset",
        fontsize=13, fontweight="bold", pad=14,
    )

    plt.tight_layout()
    out_path = os.path.join(FIGURES_DIR, "filter_funnel.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved {out_path}")


if __name__ == "__main__":
    build_pipeline()
    build_funnel()
