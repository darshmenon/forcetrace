"""CSV loading with flexible column mapping."""
import csv

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
}


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


def load(path, cols=None):
    """Read a CSV into {'t', 'f_axial'?, 'f_lateral'?, 'force'?, 'depth'?, 'z'?, 'x'?, 'y'?, 'mode'?} float arrays.

    Raises ValueError with the headers found if no time or force column can be resolved.
    """
    cols = cols or {}
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
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
    order = np.argsort(data["t"], kind="stable")
    if not np.all(order == np.arange(len(order))):
        data = {k: v[order] for k, v in data.items()}
    if "force" not in data:
        a = data["f_axial"]
        l = data.get("f_lateral", np.zeros_like(a))
        data["force"] = np.hypot(a, l)
    if "f_axial" not in data:
        data["f_axial"] = data["force"]
    return data
