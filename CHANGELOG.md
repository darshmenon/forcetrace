# Changelog

## 0.2.0
- `forcetrace map`: top-down contact map PNG, tip path coloured by force, hole outline and insert zone, start/end/peak markers.
- `forcetrace animate`: GIF with the tip path coloured by force next to force vs time, a moving cursor and shaded task phases.
- `forcetrace dashboard`: one self-contained HTML page (inline SVG and JS, no CDN) with per-run metric cards, overlaid force, depth and top-down plots, hover read-outs, run toggles and a log-scale switch.
- Loader reads `x` and `y` columns (`tip_x`, `pos_x`, ...); `examples/export_mujoco_ur3.py` now writes them. The MuJoCo example CSVs were regenerated with the same data plus `x`, `y`.
- New options: `--hole X Y`, `--hole-half`, `--peg-radius`, `--fps`, `--seconds`.

## 0.1.0
- `forcetrace analyze run.csv`: metrics table (+ `--json`) and an annotated plot (`--plot`) for one run: peak force, impulse, time in contact, first contact, insertion time and depth, jam detection, axial overshoot and settling time.
- `forcetrace compare a.csv b.csv ...`: side-by-side metrics table and an overlaid plot (`--out`, `--logy`).
- Flexible CSV input: common column aliases, `--cols name=header` to map your own, force magnitude derived from axial + lateral when absent, depth from `--surface-z` and a z column.
- With a depth column, force only counts as contact near the surface (`--surface-tol`), so a commanded spring force during free descent is not reported as contact.
- Examples: UR3 Gazebo and MuJoCo peg-in-hole logs in `examples/data`, and `examples/export_mujoco_ur3.py` to regenerate the MuJoCo ones.
