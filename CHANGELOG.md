# Changelog

## 0.3.0
- `pip install` works from a clean virtualenv, from a clone and from the GitHub URL; the install and the `forcetrace` command were checked in a fresh venv. Python 3.10 or newer is now declared, which is what the dependencies need.
- `--json` is strict JSON: NaN and inf become `null`, numpy values become plain numbers, output ends in a newline, and `compare --json -` now prints to stdout like `analyze` does.
- Rows with NaN or inf are dropped with a note on stderr, and a file with none left is an error.
- Friendly one-line errors with exit code 2 for a missing file, a directory, an unreadable or non-text file.
- `python3 -m forcetrace` works, and Ctrl-C exits quietly with code 130.
- CI on GitHub Actions: Python 3.10 and 3.12, pip install, pytest and a CLI smoke test on the example logs.
- README starts with a quick start and the animated run.
- `--force-kind commanded|measured|simulated` labels every plot, map, animation and the compare legend with what the force is. A log with `f_meas_axial` / `f_meas_lateral` columns uses them as measured force and draws the commanded force dashed next to it.

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
