#!/usr/bin/env python3
"""Generate the four figures for the PSDL Qeios article.

Run from the repository root with the project venv:
    venv/bin/python docs/figures/make_figures.py

Outputs fig1..fig4 as .png (300 dpi), .pdf, and .svg into docs/figures/.
All numbers come from scripts/experiment_aki_mimic_results.json and the
pre-gate run reported in the article text.
"""

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = pathlib.Path(__file__).parent

INK = "#1f2430"        # primary text / borders
MUTED = "#6b7280"      # secondary text
EDGE = "#8b93a3"       # normal dataflow edges
BLUE = "#4269d0"       # accent / gated series / highlighted path
ORANGE = "#ff725c"     # ungated series
RED = "#a63d2f"        # NOT edges
BOX_BG = "#f4f6fa"
BOX_BG2 = "#eef1f7"

plt.rcParams.update({
    "font.size": 9.5,
    "font.family": "DejaVu Sans",
    "svg.fonttype": "none",
})


def save(fig, name):
    for ext, kw in (("png", {"dpi": 300}), ("pdf", {}), ("svg", {})):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight",
                    facecolor="white", **kw)
    plt.close(fig)
    print("wrote", name)


def box(ax, x, y, w, h, title, lines=(), bg=BOX_BG, edge=INK, lw=1.1,
        title_size=9.5, line_size=7.8, title_color=None, line_gap=0.058):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.012,rounding_size=0.014",
                                fc=bg, ec=edge, lw=lw))
    n = len(lines)
    total = n * line_gap
    cy = y + h / 2 + total / 2
    ax.text(x + w / 2, cy, title, ha="center", va="center",
            fontsize=title_size, fontweight="bold",
            color=title_color or INK)
    for ln in lines:
        cy -= line_gap
        ax.text(x + w / 2, cy, ln, ha="center", va="center",
                fontsize=line_size, color=MUTED)


def arrow(ax, p0, p1, color=INK, lw=1.3, style="-|>", shrink=2, ls="-",
          rad=0.0):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, color=color,
                                 lw=lw, linestyle=ls, mutation_scale=11,
                                 shrinkA=shrink, shrinkB=shrink,
                                 connectionstyle=f"arc3,rad={rad}"))


# ────────────────────────────── Figure 1: architecture ───────────────

def fig1():
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    ax.set_xlim(0, 1.16)
    ax.set_ylim(0, 1)
    ax.axis("off")

    box(ax, 0.02, 0.56, 0.24, 0.40, "PSDL Scenario",
        ["portable unit of exchange",
         "audit · signals",
         "trends · logic"], lw=1.4, line_gap=0.075)
    ax.text(0.14, 0.51, "WHAT to detect", ha="center", fontsize=8,
            color=MUTED, style="italic")

    box(ax, 0.02, 0.06, 0.24, 0.36, "Dataset Specification",
        ["semantic ref → table,",
         "concept id, unit"], line_gap=0.075)
    ax.text(0.14, 0.01, "WHERE to find it", ha="center", fontsize=8,
            color=MUTED, style="italic")

    box(ax, 0.35, 0.26, 0.26, 0.50, "Compiler → ScenarioIR",
        ["dependency-ordered DAG",
         "diagnostics",
         "canonical hashes",
         "(ir · spec · toolchain)"], bg=BOX_BG2, lw=1.4, title_size=9,
        line_gap=0.075)

    runtimes = [
        (0.78, "Single-patient (Python)", "per-patient trace"),
        (0.46, "Cohort (SQL)", "one query, database-side"),
        (0.14, "Streaming (Flink)", "event-by-event"),
    ]
    for y, t, sub in runtimes:
        box(ax, 0.70, y - 0.05, 0.27, 0.17, t, [sub], line_gap=0.062,
            title_size=9)

    arrow(ax, (0.26, 0.72), (0.35, 0.60), lw=1.4)
    arrow(ax, (0.26, 0.24), (0.35, 0.42), lw=1.4)
    for y, _, _ in runtimes:
        arrow(ax, (0.61, 0.51), (0.70, y + 0.035), lw=1.4)

    arrow(ax, (0.99, 0.76), (0.99, 0.52), color=BLUE, lw=1.6,
          style="<|-|>", rad=-0.35)
    ax.text(1.005, 0.64, "conformance audit:\noutput-by-output\ncomparison (§5.3)",
            ha="left", va="center", fontsize=8, color=BLUE)
    save(fig, "fig1_architecture")


# ────────────────────────────── Figure 2: scenario DAG ───────────────

W, H = 0.152, 0.115


def _node(ax, x, y, name, sub=None, fired=False):
    ec = BLUE if fired else INK
    box(ax, x - W / 2, y - H / 2, W, H, name,
        [sub] if sub else [], edge=ec, lw=2.0 if fired else 1.0,
        title_size=8.3, line_size=7.0, line_gap=0.05,
        title_color=BLUE if fired else INK)
    return (x, y)


def fig2():
    fig, ax = plt.subplots(figsize=(11.5, 7.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    for y, label in ((0.90, "SIGNALS"), (0.71, "TRENDS"), (0.41, "LOGIC")):
        ax.text(0.995, y, label, fontsize=8.5, color=MUTED,
                fontweight="bold", va="center", ha="right")

    n = lambda *a, **k: _node(ax, *a, **k)
    cr = n(0.30, 0.90, "Cr", "creatinine", fired=True)
    bun = n(0.70, 0.90, "BUN", "blood urea nitrogen")

    t_cur = n(0.09, 0.71, "cr_current", "last(Cr) = 2.5", fired=True)
    t_ratio = n(0.27, 0.71, "cr_ratio", "last/min(7d) = 2.5", fired=True)
    t_rise = n(0.45, 0.71, "cr_rise_48h", "last − min(48h)")
    t_slope = n(0.62, 0.71, "cr_slope_24h", "slope(Cr, 24h)")
    t_bcr = n(0.86, 0.71, "bun_cr_ratio", "last(BUN)/last(Cr)")

    l_def = n(0.18, 0.50, "aki_definition_met", "rise OR ratio ≥ 1.5",
              fired=True)
    l_rise = n(0.45, 0.50, "cr_rise_flag", "rise ≥ 0.3")
    l_fall = n(0.62, 0.50, "cr_falling", "slope < −3e−6")
    l_pp = n(0.86, 0.50, "prerenal_pattern", "BUN:Cr > 20")

    l_s3 = n(0.09, 0.30, "aki_stage3", "ratio≥3 OR (Cr≥4 & def)")
    l_s2 = n(0.31, 0.30, "aki_stage2", "ratio ≥ 2 AND NOT s3", fired=True)
    l_s1 = n(0.53, 0.30, "aki_stage1", "def, NOT s2, NOT s3")

    l_pres = n(0.31, 0.10, "aki_present", "s1 OR s2 OR s3", fired=True)
    l_rec = n(0.62, 0.10, "aki_recovering", "present AND falling")
    l_pl = n(0.86, 0.10, "prerenal_likely", "s1 AND pattern")

    def down(a, b, hot=False, rad=0.0, inhib=False):
        arrow(ax, (a[0], a[1] - H / 2), (b[0], b[1] + H / 2),
              color=RED if inhib else (BLUE if hot else EDGE),
              lw=1.8 if hot else 0.95,
              ls=(0, (4, 3)) if inhib else "-", rad=rad)

    def side(a, b, inhib=False, hot=False, rad=0.0):
        sx = 1 if b[0] > a[0] else -1
        arrow(ax, (a[0] + sx * W / 2, a[1]), (b[0] - sx * W / 2, b[1]),
              color=RED if inhib else (BLUE if hot else EDGE),
              lw=1.8 if hot else 0.95,
              ls=(0, (4, 3)) if inhib else "-", rad=rad)

    down(cr, t_cur); down(cr, t_ratio, hot=True); down(cr, t_rise)
    down(cr, t_slope); down(cr, t_bcr, rad=0.22); down(bun, t_bcr)

    down(t_rise, l_rise)
    down(t_ratio, l_def)
    side(l_rise, l_def, rad=0.15)

    down(l_def, l_s3)
    down(t_cur, l_s3)
    down(t_ratio, l_s3, rad=0.3)
    down(t_ratio, l_s2, hot=True)
    down(l_def, l_s1, rad=-0.18)
    side(l_s3, l_s2, inhib=True)
    side(l_s2, l_s1, inhib=True)
    down(l_s3, l_s1, inhib=True, rad=-0.32)

    down(l_s3, l_pres, rad=0.12)
    down(l_s2, l_pres, hot=True)
    down(l_s1, l_pres, rad=-0.12)

    down(t_slope, l_fall)
    down(l_fall, l_rec)
    side(l_pres, l_rec)
    down(t_bcr, l_pp)
    down(l_pp, l_pl)
    down(l_s1, l_pl, rad=-0.12)

    ax.plot([], [], color=EDGE, lw=1, label="dataflow")
    ax.plot([], [], color=RED, lw=1, ls=(0, (4, 3)),
            label="NOT (exclusive staging)")
    ax.plot([], [], color=BLUE, lw=1.8,
            label="worked example: cr_ratio = 2.5 → Stage 2")
    ax.legend(loc="lower left", fontsize=8.2, frameon=False,
              bbox_to_anchor=(-0.01, -0.02))
    save(fig, "fig2_scenario_dag")


# ────────────────────────────── Figure 3: gate impact ────────────────

def fig3():
    stages = ["Stage 1", "Stage 2", "Stage 3"]
    ungated = [16955, 5375, 11917]   # pre-gate scenario, same protocol
    gated = [16961, 5372, 8119]      # aki_definition_met gate applied

    fig, ax = plt.subplots(figsize=(7, 4.4))
    x = range(len(stages))
    w = 0.36
    b1 = ax.bar([i - w / 2 for i in x], ungated, w, color=ORANGE,
                label="without AKI-definition gate", edgecolor="white",
                linewidth=1)
    b2 = ax.bar([i + w / 2 for i in x], gated, w, color=BLUE,
                label="with AKI-definition gate (KDIGO-correct)",
                edgecolor="white", linewidth=1)
    for bars in (b1, b2):
        for r in bars:
            ax.annotate(f"{int(r.get_height()):,}",
                        (r.get_x() + r.get_width() / 2, r.get_height()),
                        textcoords="offset points", xytext=(0, 3),
                        ha="center", fontsize=8.5, color=INK)
    ax.annotate("−3,798 patients:\nchronic Cr ≥ 4.0 mg/dL,\nno acute change",
                xy=(2 + w / 2 + 0.12, 8500), xytext=(1.30, 14200),
                fontsize=8.5, color=INK, ha="left",
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1))
    ax.set_xticks(list(x))
    ax.set_xticklabels(stages)
    ax.set_ylabel("patients (exclusive stage assignment)")
    ax.set_ylim(0, 19000)
    ax.set_yticks(range(0, 20000, 4000))
    ax.set_yticklabels([f"{v:,}" for v in range(0, 20000, 4000)])
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, color="#e5e7eb", lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5, loc="lower center",
              bbox_to_anchor=(0.5, 1.0), ncol=2)
    save(fig, "fig3_gate_impact")


# ────────────────────────────── Figure 4: audit protocol ─────────────

def fig4():
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    y1, y2, bh = 0.66, 0.30, 0.26
    box(ax, 0.02, y1, 0.20, bh, "MIMIC-IV / OMOP",
        ["287M measurement rows", "294,788 patients with Cr"],
        line_gap=0.062, title_size=9)
    box(ax, 0.28, y1, 0.20, bh, "Compiled SQL",
        ["126 lines, 1.2 ms", "peak-Cr anchor per patient"],
        line_gap=0.062, title_size=9)
    box(ax, 0.54, y1, 0.20, bh, "Staged cohort",
        ["294,788 rows", "10 logic outputs each"],
        line_gap=0.062, title_size=9)
    box(ax, 0.79, y1 - 0.20, 0.19, bh + 0.08, "Comparator",
        ["20,000 / 20,000 agree", "mismatch ≤ 1.8×10⁻⁴", "(97.5% CI bound)"],
        edge=BLUE, lw=1.6, line_gap=0.062, title_size=9)
    box(ax, 0.54, y2, 0.20, bh, "Random sample",
        ["2,000 patients", "raw Cr + BUN series"],
        line_gap=0.062, title_size=9)
    box(ax, 0.28, y2, 0.20, bh, "Python runtime",
        ["independent re-evaluation", "at the same anchors"],
        line_gap=0.062, title_size=9)

    m1 = y1 + bh / 2
    m2 = y2 + bh / 2
    arrow(ax, (0.22, m1), (0.28, m1), lw=1.4)
    arrow(ax, (0.48, m1), (0.54, m1), lw=1.4)
    arrow(ax, (0.74, m1), (0.79, m1 - 0.06), lw=1.4)
    arrow(ax, (0.64, y1), (0.64, y2 + bh), lw=1.4)
    arrow(ax, (0.54, m2), (0.48, m2), lw=1.4)
    ax.plot([0.38, 0.38, 0.765], [y2 + bh, 0.615, 0.615],
            color=INK, lw=1.4, solid_capstyle="round", zorder=1)
    arrow(ax, (0.765, 0.615), (0.79, 0.575), lw=1.4)

    ax.text(0.02, 0.16, "Defects caught by earlier iterations of this audit:",
            fontsize=8.8, color=INK, fontweight="bold")
    ax.text(0.02, 0.075,
            "1  arithmetic trend silently mis-compiled (valid SQL, wrong values)"
            "      2  pointwise window divergence (1 patient in 294,788)"
            "      3  ordering of simultaneous observations (spec gap)",
            fontsize=8.0, color=MUTED)
    save(fig, "fig4_audit_protocol")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
