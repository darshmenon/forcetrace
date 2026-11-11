#!/usr/bin/env python3
"""Run the UR3 MuJoCo peg-in-hole env (ur_force_control.peg_in_hole_env) and write one CSV per case.

  python3 examples/export_mujoco_ur3.py --repo ~/UR3_ROS2_PICK_AND_PLACE/ur_force_control --out examples/data

Columns: t, x, y (tip, m, root frame; hole centre is at 0.28, 0.14), depth (m, 0 = hole top face, negative above),
f_axial, f_lateral (hole-wall force), f_total, mode.
These are MEASURED contact forces from MuJoCo, unlike the commanded spring forces in the Gazebo logs.
"""
import argparse
import csv
import os
import sys

CASES = [  # name, lateral offset (m), spiral search
    ("mujoco_ur3_off0.4mm_plain", 0.0004, False),
    ("mujoco_ur3_off1.5mm_plain", 0.0015, False),
    ("mujoco_ur3_off1.5mm_spiral", 0.0015, True),
    ("mujoco_ur3_off2.5mm_spiral", 0.0025, True),
    ("mujoco_ur3_off4mm_spiral", 0.004, True),
]

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True, help="path to the ur_force_control package directory (contains ur_force_control/)")
ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
a = ap.parse_args()
sys.path.insert(0, os.path.expanduser(a.repo))
from ur_force_control.peg_in_hole_env import PegInHole  # noqa: E402

env = PegInHole()
for name, off, search in CASES:
    r = env.run(k_lin=800.0, lateral_offset=(off, 0.0), t_end=18.0, search=search, r_max=0.006)
    path = os.path.join(a.out, name + ".csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "x", "y", "depth", "f_axial", "f_lateral", "f_total", "mode"])
        for i in range(len(r["t"])):
            w.writerow([f"{r['t'][i]:.4f}", f"{r['tip'][i][0]:.5f}", f"{r['tip'][i][1]:.5f}", f"{r['depth'][i]:.5f}", f"{r['axial'][i]:.3f}", f"{r['wall'][i]:.3f}",
                        f"{r['total'][i]:.3f}", int(r["mode"][i])])
    print(f"{name}: inserted={r['inserted']} -> {path}")
