#!/usr/bin/env python3
"""Render the LongMemEval retrieval pilot's size–recall trade-off as PNG.

This optional reporting utility requires Matplotlib. The benchmark runner and
manifest validator themselves use only the Python standard library.
"""

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.summary.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    conditions = summary["conditions"]
    full = conditions["flat_bm25"]
    recency = conditions["recency"]

    pointers = []
    for name, metrics in conditions.items():
        match = re.fullmatch(r"pointer_bm25_t([0-9]+)", name)
        if match:
            pointers.append((int(match.group(1)), metrics))
    pointers.sort(reverse=True)

    full_size = full["mean_index_chars"] / 1000
    x_values = [full_size] + [metrics["mean_index_chars"] / 1000 for _, metrics in pointers]
    y_values = [full["retrieval_recall_at_k"] * 100] + [
        metrics["retrieval_recall_at_k"] * 100 for _, metrics in pointers
    ]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 13,
            "axes.titlesize": 25,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
        }
    )
    fig, ax = plt.subplots(figsize=(16, 9), dpi=100, facecolor="#ffffff")
    ax.set_facecolor("#ffffff")

    blue = "#2563eb"
    navy = "#172554"
    orange = "#ea580c"
    grid = "#dbe3ef"
    muted = "#536179"

    ax.plot(x_values, y_values, color=blue, linewidth=2.8, zorder=2)
    ax.scatter(x_values, y_values, s=120, color=blue, edgecolor="#ffffff", linewidth=2, zorder=3)

    ax.annotate(
        f"Full text\n{y_values[0]:.1f}% recall",
        (x_values[0], y_values[0]),
        xytext=(-14, -16),
        textcoords="offset points",
        ha="right",
        va="top",
        color=navy,
        fontweight="bold",
    )
    label_positions = {
        96: (38, 79, "left"),
        48: (19.5, 58, "left"),
        24: (7.5, 75, "left"),
        12: (5.5, 44, "left"),
    }
    for (term_count, metrics), x_value, y_value in zip(pointers, x_values[1:], y_values[1:]):
        reduction = 100 * (1 - metrics["mean_index_chars"] / full["mean_index_chars"])
        label_x, label_y, alignment = label_positions[term_count]
        ax.annotate(
            f"{term_count}-term pointer\n{y_value:.1f}% recall · {reduction:.1f}% smaller",
            (x_value, y_value),
            xytext=(label_x, label_y),
            textcoords="data",
            ha=alignment,
            va="center",
            color=navy,
            fontweight="bold",
            arrowprops={"arrowstyle": "-", "color": grid, "linewidth": 1.2},
        )

    recency_recall = recency["retrieval_recall_at_k"] * 100
    ax.axhline(recency_recall, color=orange, linewidth=2, linestyle=(0, (5, 5)), zorder=1)
    ax.text(
        5.1,
        recency_recall + 2.2,
        f"Recency-only baseline: {recency_recall:.1f}%",
        color=orange,
        fontweight="bold",
        ha="left",
    )

    ax.set_xscale("log")
    ax.set_xlim(4.5, 700)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Mean indexed source text (thousand characters, log scale)", labelpad=14)
    ax.set_ylabel("Answer-session recall@3", labelpad=14)
    ax.set_title("Compact keyword pointers save space—but lose evidence", loc="left", color=navy, pad=34, fontweight="bold")
    ax.text(
        0,
        1.025,
        "A clean-room public pilot reveals a measurable compression–retrieval trade-off.",
        transform=ax.transAxes,
        color=muted,
        ha="left",
        va="bottom",
    )

    ax.grid(axis="y", color=grid, linewidth=1)
    ax.grid(axis="x", visible=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(grid)
    ax.spines["bottom"].set_color(grid)
    ax.tick_params(colors=muted)

    fig.text(
        0.075,
        0.035,
        "LongMemEval-S cleaned · 500 questions · top-3 retrieval · no reader LLM · clean-room pointer pilot",
        color=muted,
        ha="left",
    )
    fig.text(
        0.925,
        0.035,
        "Negative results are part of the evidence.",
        color=orange,
        ha="right",
        fontweight="bold",
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.09, right=0.94, top=0.82, bottom=0.16)
    fig.savefig(args.output, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    main()
