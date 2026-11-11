"""CSV loading with flexible column mapping."""
import csv
import sys

import numpy as np

# canonical name -> accepted header aliases (first match wins)
ALIASES = {
    "t": ["t", "time", "stamp", "timestamp", "sec"],
    "f_axial": ["f_axial", "fz", "force_z", "f_z", "axial"],
    "f_lateral": ["f_lateral", "fxy", "force_xy", "f_xy", "lateral"],
    "force": ["force", "f", "f_mag", "force_norm", "fnorm"],
    "depth": ["depth", "insertion_depth", "d"],
    "z": ["z", "tip_z", "pos_z"],
    "x": ["x", "tip_x", "pos_x"],
    "y": ["y", "tip_y", "pos_y"],
    "mode": ["mode", "phase", "state"],
    "f_meas_axial": ["f_meas_axial"],      # optional measured columns next to commanded ones
    "f_meas_lateral": ["f_meas_lateral"],
}

KINDS = ("commanded", "measured", "simulated")


def force_label(d, extra=""):
    """Axis label that says what kind of force the run holds, when known."""
    kind = d.get("_kind") if hasattr(d, "get") else None
    base = {"commanded": "commanded force (N)", "measured": "measured force (N)",
            "simulated": "simulated contact force (N)"}.get(kind, "force (N)")
    return base + extra


def parse_cols(spec):
    """'f_axial=Fz,t=time' -> {'f_axial': 'Fz', 't': 'time'}"""
    out = {}
    for part in (spec or "").split(","):
        if part.strip():
            k, _, v = part.partition("=")
            if not v:
                raise ValueError(f"bad --cols entry '{part}', expected name=header")
            out[k.strip()] = v.strip()
    return out


def load(path, cols=None, kind=None):
    """Read a CSV into {'t', 'f_axial'?, 'f_lateral'?, 'force'?, 'depth'?, 'z'?, 'x'?, 'y'?, 'mode'?} float arrays.

    kind says what the force is: 'commanded' (controller spring force), 'measured' (sensor) or 'simulated'
    (contact force from a simulator); it only labels plots. If the CSV has f_meas_axial / f_meas_lateral columns they
    are used as the force (kind 'measured') unless kind is 'commanded', and the commanded force is kept as f_cmd.
    The kind is stored under the key '_kind'.

    Raises ValueError with the headers found if no time or force column can be resolved.
    """
    if kind is not None and kind not in KINDS:
        raise ValueError(f"force kind must be one of {', '.join(KINDS)}, not '{kind}'")
    cols = cols or {}
    try:
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        raise ValueError(f"{path}: file not found") from None
    except IsADirectoryError:
        raise ValueError(f"{path}: is a directory, expected a CSV file") from None
    except PermissionError:
        raise ValueError(f"{path}: permission denied") from None
    except (UnicodeDecodeError, csv.Error):
        raise ValueError(f"{path}: not a text CSV file") from None
    if len(rows) < 2:
        raise ValueError(f"{path}: no data rows")
    header = [h.strip() for h in rows[0]]
    lower = {h.lower(): i for i, h in enumerate(header)}
    data = {}
    for key, names in ALIASES.items():
        want = [cols[key]] if key in cols else names
        idx = next((lower[n.lower()] for n in want if n.lower() in lower), None)
        if idx is None:
            if key in cols:
                raise ValueError(f"{path}: column '{cols[key]}' (for {key}) not found; headers: {header}")
            continue
        try:
            data[key] = np.array([float(r[idx]) for r in rows[1:] if r], dtype=float)
        except (ValueError, IndexError) as e:
            raise ValueError(f"{path}: column '{header[idx]}' is not numeric ({e})") from None
    if "t" not in data:
        raise ValueError(f"{path}: no time column found; headers: {header} (use --cols t=<header>)")
    if not any(k in data for k in ("f_axial", "force")):
        raise ValueError(f"{path}: no force column found; headers: {header} (use --cols f_axial=<header> or force=<header>)")
    good = np.ones(len(data["t"]), dtype=bool)
    for v in data.values():
        good &= np.isfinite(v)
    if not good.all():
        print(f"forcetrace: {path}: dropped {int((~good).sum())} row(s) with NaN or inf", file=sys.stderr)
        data = {k: v[good] for k, v in data.items()}
        if len(data["t"]) < 1:
            raise ValueError(f"{path}: no finite data rows")
    order = np.argsort(data["t"], kind="stable")
    if not np.all(order == np.arange(len(order))):
        data = {k: v[order] for k, v in data.items()}
    if "f_meas_axial" in data and "force" not in data and kind != "commanded":
        ca, cl = data.get("f_axial"), data.get("f_lateral", 0.0)
        if ca is not None:
            data["f_cmd"] = np.hypot(ca, cl)
        data["f_axial"] = data.pop("f_meas_axial")
        if "f_meas_lateral" in data:
            data["f_lateral"] = data.pop("f_meas_lateral")
        else:
            data.pop("f_lateral", None)
        kind = "measured"
    data.pop("f_meas_axial", None)
    data.pop("f_meas_lateral", None)
    if "force" not in data:
        a = data["f_axial"]
        l = data.get("f_lateral", np.zeros_like(a))
        data["force"] = np.hypot(a, l)
    if "f_axial" not in data:
        data["f_axial"] = data["force"]
    data["_kind"] = kind
    return data
