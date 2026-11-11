"""forcetrace command line."""
import argparse
import json
import math
import os
import sys

from forcetrace import __version__
from forcetrace.io import load, parse_cols
from forcetrace.metrics import Params, analyze, verdict
from forcetrace.viz import HOLE_HALF, PEG_R

ROWS = [
    ("verdict", None, ""),
    ("duration", "duration_s", "s"),
    ("peak force", "peak_force_n", "N"),
    ("peak axial", "peak_axial_n", "N"),
    ("peak lateral", "peak_lateral_n", "N"),
    ("impulse in contact", "impulse_ns", "N*s"),
    ("time in contact", "time_in_contact_s", "s"),
    ("first contact at", "first_contact_t", "s"),
    ("mean force in contact", "mean_force_in_contact_n", "N"),
    ("max depth", "max_depth_m", "m"),
    ("final depth", "final_depth_m", "m"),
    ("inserted at", "insertion_t", "s"),
    ("contact to insertion", "time_to_insert_s", "s"),
    ("jammed since", "jam_t", "s"),
    ("steady axial force", "steady_force_n", "N"),
    ("axial overshoot", "overshoot_pct", "%"),
    ("settling time", "settling_time_s", "s"),
]


def _plain(v):
    """Metrics as plain JSON types: numpy scalars to Python, NaN and inf to null."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def dumps(obj):
    """Strict JSON (never NaN or Infinity), 2-space indent, trailing newline, key order as produced."""
    return json.dumps(_plain(obj), indent=2, allow_nan=False) + "\n"


def _fmt(v, unit):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return f"{v:.4g} {unit}".strip() if unit in ("m",) else f"{v:.3f} {unit}".strip()


def table(m, name=""):
    lines = [f"{name}"] if name else []
    for label, key, unit in ROWS:
        if key is None:
            lines.append(f"  {label:<24}{verdict(m)}")
        elif key in m:
            lines.append(f"  {label:<24}{_fmt(m[key], unit)}")
    return "\n".join(lines)


def _params(a):
    return Params(contact_n=a.contact_n, insert_depth=a.insert_depth, jam_time=a.jam_time, surface_z=a.surface_z,
                  surface_tol=None if a.no_depth_gate else a.surface_tol)


def _modes(spec):
    out = {}
    for part in (spec or "").split(","):
        if part.strip():
            k, _, v = part.partition(":")
            out[int(k)] = v.strip()
    return out


def _common(sp):
    sp.add_argument("--cols", help="column mapping, e.g. t=time,f_axial=Fz,f_lateral=Fxy,depth=d,mode=phase,force=|F|")
    sp.add_argument("--force-kind", choices=["commanded", "measured", "simulated"],
                    help="what the force column is, for plot labels; a log with f_meas_axial/f_meas_lateral columns "
                         "uses them as measured force unless this is 'commanded'")
    sp.add_argument("--contact-n", type=float, default=0.5, help="axial force (N) that counts as contact [0.5]")
    sp.add_argument("--insert-depth", type=float, default=0.027, help="depth (m) that counts as inserted [0.027]")
    sp.add_argument("--jam-time", type=float, default=3.0, help="seconds of contact without progress that is a jam [3]")
    sp.add_argument("--surface-tol", type=float, default=0.002,
                    help="with a depth column, force only counts as contact within this many m above the surface [0.002]")
    sp.add_argument("--no-depth-gate", action="store_true", help="count any axial force above --contact-n as contact")
    sp.add_argument("--surface-z", type=float, help="derive depth = surface_z - z when there is no depth column")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="forcetrace", description="Contact-force metrics and plots for manipulation runs.")
    ap.add_argument("--version", action="version", version=f"forcetrace {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze", help="metrics (table + optional JSON) and an annotated plot for one CSV")
    an.add_argument("csv")
    _common(an)
    an.add_argument("--json", metavar="PATH", help="write metrics as JSON ('-' for stdout)")
    an.add_argument("--plot", metavar="PNG", help="write the annotated plot")
    an.add_argument("--modes", help="label task modes in the plot, e.g. 0:descend,1:search,2:insert")
    an.add_argument("--title")
    cp = sub.add_parser("compare", help="overlay several runs and print a metrics table")
    cp.add_argument("csv", nargs="+")
    _common(cp)
    cp.add_argument("--out", metavar="PNG", help="write the overlay plot")
    cp.add_argument("--logy", action="store_true", help="symlog force axis (for runs with large spikes)")
    cp.add_argument("--title")
    cp.add_argument("--json", metavar="PATH", help="write metrics as JSON ('-' for stdout)")
    def _viz(sp):
        _common(sp)
        sp.add_argument("--hole", nargs=2, type=float, metavar=("X", "Y"), help="hole centre in the log's frame (m); draws the hole outline")
        sp.add_argument("--hole-half", type=float, default=HOLE_HALF, help="half-width of the square hole (m) [0.0105]")
        sp.add_argument("--peg-radius", type=float, default=PEG_R, help="peg radius (m); insert zone = hole half-width - peg radius [0.01]")
        sp.add_argument("--title")
    mp = sub.add_parser("map", help="top-down contact map PNG: tip path coloured by force")
    mp.add_argument("csv")
    _viz(mp)
    mp.add_argument("--out", required=True, metavar="PNG")
    am = sub.add_parser("animate", help="animated GIF: tip path coloured by force next to force vs time")
    am.add_argument("csv")
    _viz(am)
    am.add_argument("--out", required=True, metavar="GIF")
    am.add_argument("--modes", default="0:descend,1:search,2:insert", help="mode labels, '' for none")
    am.add_argument("--fps", type=int, default=12)
    am.add_argument("--seconds", type=float, default=8.0, help="playback length of the run [8]")
    db = sub.add_parser("dashboard", help="one self-contained HTML page for several runs")
    db.add_argument("csv", nargs="+")
    _viz(db)
    db.add_argument("--out", required=True, metavar="HTML")
    a = ap.parse_args(argv)
    try:
        cols, p = parse_cols(a.cols), _params(a)
        if a.cmd == "analyze":
            d = load(a.csv, cols, a.force_kind)
            m = analyze(d, p)
            if a.json == "-":
                sys.stdout.write(dumps(m))
            else:
                print(table(m, os.path.basename(a.csv)))
                if a.json:
                    with open(a.json, "w") as f:
                        f.write(dumps(m))
            if a.plot:
                from forcetrace.plot import run_plot
                run_plot(d, m, a.plot, a.title or os.path.splitext(os.path.basename(a.csv))[0], _modes(a.modes), p)
        elif a.cmd in ("map", "animate"):
            d = load(a.csv, cols, a.force_kind)
            m = analyze(d, p)
            name = a.title or os.path.splitext(os.path.basename(a.csv))[0]
            if a.cmd == "map":
                from forcetrace.viz import contact_map
                contact_map(d, m, a.out, a.hole, a.hole_half, name, a.peg_radius)
            else:
                from forcetrace.viz import animate
                n = animate(d, m, a.out, a.hole, a.hole_half, _modes(a.modes), name, a.fps, a.seconds, peg_r=a.peg_radius)
                print(f"{a.out}: {n} frames")
        elif a.cmd == "dashboard":
            from forcetrace.dashboard import write_dashboard
            runs = []
            for f in a.csv:
                d = load(f, cols, a.force_kind)
                runs.append((os.path.splitext(os.path.basename(f))[0], d, analyze(d, p)))
            write_dashboard(runs, a.out, a.hole, a.hole_half - a.peg_radius, a.title or "forcetrace dashboard")
            print(f"{a.out}: {len(runs)} runs")
        else:
            if len(a.csv) < 2:
                raise ValueError("compare needs at least two CSV files")
            runs = []
            for f in a.csv:
                d = load(f, cols, a.force_kind)
                runs.append((os.path.splitext(os.path.basename(f))[0], d, analyze(d, p)))
            names = [r[0] for r in runs]
            w = max(len(n) for n in names) + 2
            if a.json == "-":
                sys.stdout.write(dumps({n: m for n, _, m in runs}))
            else:
                print(f"{'':<24}" + "".join(f"{n:>{max(w, 12)}}" for n in names))
                for label, key, unit in ROWS:
                    vals = [verdict(r[2]) if key is None else (_fmt(r[2].get(key), "").strip() if key in r[2] else "-")
                            for r in runs]
                    if all(v == "-" for v in vals):
                        continue
                    print(f"{label + (' (' + unit + ')' if unit else ''):<24}" + "".join(f"{v:>{max(w, 12)}}" for v in vals))
                if a.json:
                    with open(a.json, "w") as f:
                        f.write(dumps({n: m for n, _, m in runs}))
            if a.out:
                from forcetrace.plot import compare_plot
                compare_plot(runs, a.out, a.title or "forcetrace compare", a.logy)
    except (ValueError, OSError) as e:
        print(f"forcetrace: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
