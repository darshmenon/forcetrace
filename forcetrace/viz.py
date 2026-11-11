"""Spatial visualisations: contact map (PNG) and animated run (GIF). matplotlib, Agg backend."""
import warnings

import matplotlib

warnings.filterwarnings("ignore", message="Unable to import Axes3D")
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

from forcetrace.metrics import verdict
from forcetrace.plot import PHASE_COLORS

DEFAULT_MODES = {0: "descend", 1: "search", 2: "insert"}
CMAP = "RdYlBu_r"         # blue = light touch, red = hard contact; readable on a white background
PEG_R = 0.01              # m, peg radius of the UR3 task
HOLE_HALF = 0.0105        # m, half-width of the UR3 peg-in-hole fixture (0.5 mm clearance per side)


def need_xy(d):
    if "x" not in d or "y" not in d:
        raise ValueError("no x/y columns: this view needs the tip position (use --cols x=<header>,y=<header>)")


def local_xy(d, hole):
    """Tip xy in mm, relative to the hole centre (or to the first sample when the hole is unknown)."""
    ref = np.array(hole[:2], dtype=float) if hole else np.array([d["x"][0], d["y"][0]])
    return (d["x"] - ref[0]) * 1e3, (d["y"] - ref[1]) * 1e3


def force_norm(f):
    """Colour scale that a single wall spike does not wash out: 0 .. 98th percentile (at least 2 N)."""
    return Normalize(0.0, max(2.0, float(np.percentile(f, 98))))


def _hole(ax, hole, half, peg_r):
    """Hole outline (context) and the insert zone: where the tip centre must be for the peg to drop in."""
    if not hole:
        return
    h, z = half * 1e3, (half - peg_r) * 1e3
    ax.add_patch(Rectangle((-h, -h), 2 * h, 2 * h, fill=False, ec="#9aa5b1", lw=1.2, ls="--", zorder=1))
    ax.add_patch(Rectangle((-z, -z), 2 * z, 2 * z, fill=True, fc="#d8f0dc", ec="#2ca02c", lw=1.6, zorder=1))
    ax.annotate(f"insert zone ±{z:.1f} mm", (-z, z), xytext=(-4, 5), textcoords="offset points", ha="right", fontsize=8,
                color="#1e7a34")


def _setup_xy(ax, X, Y, hole):
    ext = max(np.abs(X).max() * 1.3, np.abs(Y).max() * 1.3, 2.0)
    ax.set_xlim(-ext, ext)
    ax.set_ylim(-ext, ext)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)" + (" from hole centre" if hole else " from start"))
    ax.set_ylabel("y (mm)")
    ax.grid(alpha=0.25)


def contact_map(d, m, path, hole=None, half=HOLE_HALF, title=None, peg_r=PEG_R):
    """Top-down scatter of the tip path coloured by force, hole outline, start/end/peak markers."""
    need_xy(d)
    X, Y = local_xy(d, hole)
    f = d["force"]
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    _hole(ax, hole, half, peg_r)
    ax.plot(X, Y, color="#c8c8c8", lw=1.0, zorder=2)
    order = np.argsort(f, kind="stable")       # strongest contact drawn on top
    norm = force_norm(f)
    sc = ax.scatter(X[order], Y[order], c=f[order], s=16, cmap=CMAP, norm=norm, zorder=3, edgecolors="none")
    ax.plot(X[0], Y[0], "o", mfc="white", mec="#222", ms=7, zorder=4, label="start")
    ax.plot(X[-1], Y[-1], "s", mfc="#2ca02c" if m.get("inserted") else "#d62728", mec="#222", ms=7, zorder=4, label="end")
    k = int(np.argmax(f))
    ax.annotate(f"peak {f[k]:.1f} N", (X[k], Y[k]), xytext=(10, 10), textcoords="offset points", fontsize=8,
                arrowprops=dict(arrowstyle="-", color="#444", lw=0.6), zorder=5)
    _setup_xy(ax, X, Y, hole)
    ax.set_title(title or "contact map", loc="left", fontsize=11)
    ax.text(1.0, 1.01, verdict(m), transform=ax.transAxes, ha="right", va="bottom", fontsize=10, fontweight="bold",
            color={"INSERTED": "#2ca02c", "JAMMED": "#d62728"}.get(verdict(m), "#555"))
    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("|F| (N)" + ("" if f.max() <= norm.vmax else f", clipped at {norm.vmax:.0f}"))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _bands(ax, d, modes):
    if "mode" not in d:
        return
    t, md = d["t"], d["mode"].astype(int)
    s = 0
    for i in range(1, len(t) + 1):
        if i == len(t) or md[i] != md[s]:
            e = t[min(i, len(t) - 1)]
            ax.axvspan(t[s], e, color=PHASE_COLORS[md[s] % len(PHASE_COLORS)], alpha=0.6, lw=0, zorder=0)
            if modes.get(md[s]) and e - t[s] > 0.06 * (t[-1] - t[0]):
                ax.text((t[s] + e) / 2, 0.97, modes[md[s]], transform=ax.get_xaxis_transform(), ha="center", va="top",
                        fontsize=8, color="#555", style="italic")
            s = i


def animate(d, m, path, hole=None, half=HOLE_HALF, modes=None, title=None, fps=12, seconds=8.0, hold=1.0, dpi=72,
            peg_r=PEG_R):
    """GIF: left = top-down tip path coloured by force, right = force vs time with a moving cursor and phase bands."""
    need_xy(d)
    modes = DEFAULT_MODES if modes is None else modes
    t, f = d["t"], d["force"]
    X, Y = local_xy(d, hole)
    n_play = max(2, int(fps * seconds))
    idx = np.unique(np.linspace(0, len(t) - 1, n_play).astype(int))
    idx = np.concatenate([idx, np.full(int(fps * hold), idx[-1])])          # hold the last frame

    fig, (axm, axf) = plt.subplots(1, 2, figsize=(10.4, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})
    norm = force_norm(f)
    cmap = plt.get_cmap(CMAP)
    _hole(axm, hole, half, peg_r)
    _setup_xy(axm, X, Y, hole)
    segs = np.stack([np.column_stack([X[:-1], Y[:-1]]), np.column_stack([X[1:], Y[1:]])], axis=1)
    ghost = LineCollection(segs, colors="#d5d5d5", linewidths=1.0, zorder=2)
    axm.add_collection(ghost)
    trail = LineCollection([], cmap=cmap, norm=norm, linewidths=2.6, zorder=3)
    axm.add_collection(trail)
    dot, = axm.plot([], [], "o", mfc="white", mec="#222", ms=9, zorder=5)
    cb = fig.colorbar(trail, ax=axm, fraction=0.046, pad=0.03)
    cb.set_label("|F| (N)")
    axm.set_title("peg tip, top-down", loc="left", fontsize=10)

    _bands(axf, d, modes)
    big = f.max() > 6 * max(1.0, np.percentile(f, 95))
    axf.plot(t, f, color="#ccc", lw=1.0, zorder=1)
    line, = axf.plot([], [], color="#1f77b4", lw=1.8, zorder=3)
    cur = axf.axvline(t[0], color="#222", lw=1.0, zorder=4)
    axf.set_xlim(t[0], t[-1])
    if big:
        axf.set_yscale("symlog", linthresh=1.0)
    axf.set_ylim(0, f.max() * 1.1)
    axf.set_xlabel("time (s)")
    axf.set_ylabel("force (N)" + (", symlog" if big else ""))
    axf.grid(alpha=0.25)
    k = int(np.argmax(f))
    axf.annotate(f"peak {f[k]:.1f} N", (t[k], f[k]), xytext=(-8, -22), textcoords="offset points", ha="right", fontsize=8,
                 arrowprops=dict(arrowstyle="-", color="#444", lw=0.6))
    axf.set_title(title or "contact force", loc="left", fontsize=10)
    axf.text(1.0, 1.02, verdict(m), transform=axf.transAxes, ha="right", va="bottom", fontsize=10, fontweight="bold",
             color={"INSERTED": "#2ca02c", "JAMMED": "#d62728"}.get(verdict(m), "#555"))
    info = axf.text(0.015, 0.80, "", transform=axf.transAxes, fontsize=8.5, family="monospace", va="top",
                    bbox=dict(fc="white", ec="none", alpha=0.75, pad=2))
    fig.tight_layout()

    def draw(j):
        i = int(idx[j])
        if i > 0:
            trail.set_segments(segs[:i])
            trail.set_array(0.5 * (f[:i] + f[1:i + 1]))
        dot.set_data([X[i]], [Y[i]])
        line.set_data(t[:i + 1], f[:i + 1])
        cur.set_xdata([t[i], t[i]])
        mode = modes.get(int(d["mode"][i]), "") if "mode" in d else ""
        txt = f"t {t[i]:5.2f} s  F {f[i]:6.1f} N"
        if "depth" in d:
            txt += f"\ndepth {d['depth'][i] * 1e3:5.1f} mm"
        info.set_text(txt + (f"\nmode {mode}" if mode else ""))
        return trail, dot, line, cur, info

    anim = FuncAnimation(fig, draw, frames=len(idx), blit=False)
    anim.save(path, writer=PillowWriter(fps=fps), dpi=dpi)
    plt.close(fig)
    return len(idx)
