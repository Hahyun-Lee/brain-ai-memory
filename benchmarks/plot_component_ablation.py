#!/usr/bin/env python3
"""Plot cumulative deterministic contract recovery for the public runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "benchmarks" / "pilots" / "component-ablation-20260715" / "summary.json"
DEFAULT_OUTPUT = ROOT / "docs" / "assets" / "component-ablation.png"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    by_name = {row["condition"]: row for row in summary["conditions"]}
    effects = summary["component_effects"]

    labels = ["Flat\nretrieval"] + [
        {
            "pfc_routing": "PFC\nrouting",
            "atl_semantic": "ATL\nsemantic",
            "hc_episodic": "HC\nepisodic",
            "ips_state": "IPS\nexact state",
            "th_gate": "TH\ninput gate",
            "bg_rules": "BG\nrules",
            "cb_sequence": "CB\nfallback",
            "consolidation": "Consolidate",
            "reconsolidation": "Reconsolidate",
            "checkpoint": "Checkpoint",
        }[item["feature"]]
        for item in effects
    ]
    values = [by_name[summary["flat_condition"]]["passed"]] + [
        item["cumulative_score"] for item in effects
    ]

    navy = "#0F172A"
    blue = "#2563EB"
    teal = "#0F766E"
    gray = "#94A3B8"
    grid = "#CBD5E1"
    colors = [gray] + [blue] * 7 + [teal] * 3

    fig, ax = plt.subplots(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    bars = ax.bar(range(len(values)), values, color=colors, width=0.72)

    ax.set_ylim(0, summary["case_count"] + 2.5)
    ax.set_yticks(range(0, summary["case_count"] + 1, 5))
    ax.set_ylabel("Contracts satisfied (out of 20)", color=navy, fontweight="bold")
    ax.set_xticks(range(len(labels)), labels)
    ax.grid(axis="y", color=grid, linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(grid)
    ax.tick_params(axis="both", colors="#475569", length=0, pad=10)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.35,
            f"{value}/20",
            ha="center",
            va="bottom",
            color=navy,
            fontweight="bold",
            fontsize=11,
        )

    ax.set_title(
        "Each added software contract recovers its designed behavior",
        loc="left",
        color=navy,
        fontsize=22,
        fontweight="bold",
        pad=34,
    )
    ax.text(
        0,
        1.015,
        "Cumulative deterministic ablation · 20 authored cases · no LLM or external API",
        transform=ax.transAxes,
        color="#475569",
        fontsize=12,
        va="bottom",
    )
    ax.text(
        0,
        -0.19,
        "The flat control retrieved the expected top text for 6/6 memory queries. "
        "Scores measure typed routing, state, gates, sequences, and lifecycle contracts—not answer quality.",
        transform=ax.transAxes,
        color="#475569",
        fontsize=11,
    )

    fig.subplots_adjust(left=0.075, right=0.985, top=0.82, bottom=0.22)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, facecolor="white")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
