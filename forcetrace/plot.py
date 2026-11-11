"""Annotated force plots (matplotlib, Agg)."""
import warnings

import matplotlib

warnings.filterwarnings("ignore", message="Unable to import Axes3D")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from forcetrace.metrics import verdict

PHASE_COLORS = ["#dbe9f6", "#fde9c9", "#d7efd9", "#f3d9ea", "#e6e6e6"]
COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]


def _phases(ax, d, modes):
    if "mode" not in d:
        return
    t, md = d["t"], d["mode"].astype(int)
    start = 0
    for i in range(1, len(t) + 1):
        if i == len(t) or md[i] != md[start]:
            k = md[start]
            ax.axvspan(t[start], t[min(i, len(t) - 1)], color=PHASE_COLORS[k % len(PHASE_COLORS)], alpha=0.55, lw=0, zorder=0)
            if modes and k in modes and t[min(i, len(t) - 1)] - t[start] > 0.04 * (t[-1] - t[0]):
                ax.text((t[start] + t[min(i, len(t) - 1)]) / 2, 0.02, modes[k], transform=ax.get_xaxis_transform(),
                        ha="center", va="bottom", fontsize=8, color="#666", style="italic")
            start = i


def run_plot(d, m, path, title=None, modes=None, p=None):
    has_depth = "depth" in d or ("z" in d and p is not None and p.surface_z is not None)
    depth = d.get("depth") if "depth" in d else (p.surface_z - d["z"] if has_depth else None)
    fig, axes = plt.subplots(2 if has_depth else 1, 1, figsize=(9, 6 if has_depth else 3.8), sharex=True, squeeze=False)
    ax = axes[0, 0]
    _phases(ax, d, modes)
    t = d["t"]
    ax.plot(t, d["force"], color="#222", lw=1.2, label="|F|")
    ax.plot(t, d["f_axial"], color=COLORS[0], lw=1.0, label="axial")
    if "f_lateral" in d:
        ax.plot(t, d["f_lateral"], color=COLORS[1], lw=1.0, label="lateral")
    ax.axhline(m["contact_threshold_n"], color="#888", ls=":", lw=0.8)
    ax.annotate(f"peak {m['peak_force_n']:.1f} N", (m["peak_force_t"], m["peak_force_n"]), xytext=(6, 6),
                textcoords="offset points", fontsize=8, arrowprops=dict(arrowstyle="-", color="#444", lw=0.6))
    if m["first_contact_t"] is not None:
        ax.axvline(m["first_contact_t"], color="#555", ls="--", lw=0.9)
        ax.text(m["first_contact_t"], 0.97, " contact", transform=ax.get_xaxis_transform(), fontsize=8, va="top", color="#555")
    if m["insertion_t"] is not None:
        ax.axvline(m["insertion_t"], color="#2ca02c", ls="--", lw=0.9)
        ax.text(m["insertion_t"], 0.85, "inserted ", transform=ax.get_xaxis_transform(), fontsize=8, va="top", ha="right", color="#2ca02c")
    if m["jam_t"] is not None:
        ax.axvspan(m["jam_t"], t[-1], color="#d62728", alpha=0.10, lw=0)
        ax.text(m["jam_t"], 0.97, " jammed", transform=ax.get_xaxis_transform(), fontsize=8, va="top", color="#d62728")
    ax.set_ylabel("force (N)")
    ax.set_title(title or "contact force", loc="left", fontsize=11, pad=10)
    ax.text(1.0, 1.01, verdict(m), transform=ax.transAxes, ha="right", va="bottom", fontsize=10, fontweight="bold",
            color={"INSERTED": "#2ca02c", "JAMMED": "#d62728"}.get(verdict(m), "#555"))
    ax.legend(loc="upper left", fontsize=8, ncol=3, frameon=False, bbox_to_anchor=(0.0, 0.88))
    ax.grid(alpha=0.25)
    if has_depth:
        ad = axes[1, 0]
        ad.plot(t, depth * 1e3, color="#222", lw=1.2)
        if p is not None:
            ad.axhline(p.insert_depth * 1e3, color="#2ca02c", ls=":", lw=0.9)
            ad.text(t[0], p.insert_depth * 1e3, " inserted depth", fontsize=8, va="bottom", color="#2ca02c")
        ad.set_ylabel("depth (mm)")
        ad.set_xlabel("time (s)")
        ad.grid(alpha=0.25)
    else:
        ax.set_xlabel("time (s)")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def compare_plot(runs, path, title="forcetrace compare", logy=False):
    """runs: list of (label, data, metrics). Overlay |F| and depth."""
    has_depth = any("depth" in d for _, d, _ in runs)
    fig, axes = plt.subplots(2 if has_depth else 1, 1, figsize=(9, 6 if has_depth else 3.8), sharex=True, squeeze=False)
    for i, (lab, d, m) in enumerate(runs):
        c = COLORS[i % len(COLORS)]
        axes[0, 0].plot(d["t"], d["force"], color=c, lw=1.2, label=f"{lab}: {verdict(m).lower()}, peak {m['peak_force_n']:.1f} N")
        if has_depth and "depth" in d:
            axes[1, 0].plot(d["t"], d["depth"] * 1e3, color=c, lw=1.2)
    axes[0, 0].set_ylabel("|F| (N)" + (", log scale" if logy else ""))
    if logy:
        axes[0, 0].set_yscale("symlog", linthresh=1.0)
    axes[0, 0].set_title(title, loc="left", fontsize=11)
    axes[0, 0].legend(fontsize=8, frameon=False)
    axes[0, 0].grid(alpha=0.25)
    if has_depth:
        axes[1, 0].set_ylabel("depth (mm)")
        axes[1, 0].grid(alpha=0.25)
    axes[-1, 0].set_xlabel("time (s)")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
