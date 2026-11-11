"""Contact-force metrics for one run. Pure numpy."""
from dataclasses import dataclass

import numpy as np


@dataclass
class Params:
    contact_n: float = 0.5        # N on the contact channel (f_axial) that counts as touching
    insert_depth: float = 0.027   # m of depth that counts as inserted (0.9 x a 30 mm hole)
    jam_time: float = 3.0         # s of sustained contact with no depth progress that counts as a jam
    jam_progress: float = 0.001   # m of depth gained inside that window that still counts as progress
    settle_band: float = 0.05     # fraction of steady force
    settle_floor: float = 0.1     # N, minimum band half-width
    surface_z: float = None       # derive depth = surface_z - z when there is no depth column
    surface_tol: float = 0.002    # m above the surface within which force counts as contact; None = no depth gate


def _trapz(y, x):
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x))) if len(x) > 1 else 0.0


def analyze(d, p=Params()):
    """Metrics dict for a loaded run (see io.load). Values that do not apply are None."""
    t, fa, fm = d["t"], d["f_axial"], d["force"]
    depth = d.get("depth")
    if depth is None and "z" in d and p.surface_z is not None:
        depth = p.surface_z - d["z"]
    m = {"samples": int(len(t)), "duration_s": float(t[-1] - t[0])}
    m["peak_force_n"] = float(fm.max())
    m["peak_force_t"] = float(t[fm.argmax()])
    m["peak_axial_n"] = float(fa.max())
    if "f_lateral" in d:
        m["peak_lateral_n"] = float(d["f_lateral"].max())

    touching = fa > p.contact_n
    gated = depth is not None and p.surface_tol is not None
    if gated:                       # a commanded spring force during free descent is not contact
        touching = touching & (depth > -p.surface_tol)
    m["contact_threshold_n"] = p.contact_n
    m["contact_depth_gated"] = bool(gated)
    m["time_in_contact_s"] = _trapz(touching.astype(float), t)
    m["impulse_ns"] = _trapz(np.where(touching, fm, 0.0), t)
    ic = int(np.argmax(touching)) if touching.any() else None
    m["first_contact_t"] = float(t[ic]) if ic is not None else None
    m["mean_force_in_contact_n"] = float(fm[touching].mean()) if touching.any() else None

    m["final_depth_m"] = m["max_depth_m"] = m["insertion_t"] = m["time_to_insert_s"] = m["inserted"] = None
    ins = None
    if depth is not None:
        m["final_depth_m"] = float(depth[-1])
        m["max_depth_m"] = float(depth.max())
        hit = np.nonzero(depth >= p.insert_depth)[0]
        m["inserted"] = bool(len(hit))
        if len(hit):
            ins = int(hit[0])
            m["insertion_t"] = float(t[ins])
            if ic is not None:
                m["time_to_insert_s"] = float(max(0.0, t[ins] - t[ic]))

    # jam: contact held for jam_time while depth does not advance, and the part never went in
    m["jammed"] = None
    m["jam_t"] = None
    if depth is not None:
        m["jammed"] = False
        if not m["inserted"] and ic is not None:
            # for every sample i: the window [i, j) spans jam_time; jam if contact never broke and net depth gain is tiny
            j = np.minimum(np.searchsorted(t, t + p.jam_time), len(t) - 1)
            ok = t[j] - t >= p.jam_time - 1e-9
            bad = np.concatenate([[0], np.cumsum(~touching)])
            all_touching = (bad[j + 1] - bad[np.arange(len(t))]) == 0
            stuck = ok & all_touching & (depth[j] - depth < p.jam_progress)
            if stuck.any():
                k = int(np.argmax(stuck))
                m["jammed"], m["jam_t"] = True, float(t[k])

    # overshoot and settling of the axial force on the contact segment (first contact until insertion / end)
    m["steady_force_n"] = m["overshoot_pct"] = m["settling_time_s"] = None
    if ic is not None:
        end = ins if ins is not None and ins > ic else len(t) - 1
        seg_t, seg = t[ic:end + 1], fa[ic:end + 1]
        if len(seg) >= 10:
            tail = seg[int(len(seg) * 0.8):]
            steady = float(np.median(tail))
            m["steady_force_n"] = steady
            if steady > p.contact_n:
                m["overshoot_pct"] = float(max(0.0, (seg.max() - steady) / steady * 100.0))
                band = max(p.settle_band * steady, p.settle_floor)
                out = np.nonzero(np.abs(seg - steady) > band)[0]
                m["settling_time_s"] = float(seg_t[out[-1] + 1] - seg_t[0]) if len(out) and out[-1] + 1 < len(seg) \
                    else (0.0 if not len(out) else None)
    return m


def verdict(m):
    if m.get("inserted"):
        return "INSERTED"
    if m.get("jammed"):
        return "JAMMED"
    if m.get("inserted") is False:
        return "NOT INSERTED"
    return "NO DEPTH DATA"
