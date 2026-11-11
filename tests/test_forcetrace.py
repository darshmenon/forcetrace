import json
import os

import numpy as np
import pytest

from forcetrace.cli import main
from forcetrace.io import load, parse_cols
from forcetrace.metrics import Params, analyze, verdict

DATA = os.path.join(os.path.dirname(__file__), "..", "examples", "data")


def write_csv(path, header, rows):
    with open(path, "w") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(v) for v in r) + "\n")
    return str(path)


def synth(kind, dt=0.01, T=14.0):
    """descend 0-3 s (free air), land at 3 s, then: 'insert' drops in at 6 s; 'jam' sits at 20 N."""
    t = np.arange(0, T, dt)
    depth = np.where(t < 3, -0.03 + 0.01 * t, 0.0)
    f = np.zeros_like(t)
    if kind == "insert":
        depth = np.where(t > 6, np.minimum(0.03, 0.01 * (t - 6)), depth)
        f = np.where((t >= 3) & (t < 6), 3.0, 0.2)
    else:
        f = np.where(t >= 3, np.minimum(20.0, 20.0 * (t - 3)), 0.0)
    return {"t": t, "f_axial": f, "force": f, "depth": depth}


def test_parse_cols():
    assert parse_cols("f_axial=Fz, t=time") == {"f_axial": "Fz", "t": "time"}
    with pytest.raises(ValueError):
        parse_cols("f_axial")


def test_load_aliases_and_magnitude(tmp_path):
    p = write_csv(tmp_path / "a.csv", ["Time", "Fz", "Fxy"], [(0, 3, 4), (1, 0, 0)])
    d = load(p)
    assert np.allclose(d["force"], [5, 0]) and np.allclose(d["f_axial"], [3, 0])


def test_load_custom_cols_and_force_only(tmp_path):
    p = write_csv(tmp_path / "b.csv", ["ts", "norm"], [(0, 1.5), (1, 2.5)])
    d = load(p, {"t": "ts", "force": "norm"})
    assert np.allclose(d["f_axial"], d["force"])


def test_load_errors_name_the_headers(tmp_path):
    p = write_csv(tmp_path / "c.csv", ["a", "b"], [(1, 2), (2, 3)])
    with pytest.raises(ValueError, match="headers"):
        load(p)
    q = write_csv(tmp_path / "d.csv", ["t", "f_axial"], [(0, "x")])
    with pytest.raises(ValueError):
        load(q)
    with pytest.raises(ValueError, match="not found"):
        load(write_csv(tmp_path / "e.csv", ["t", "f_axial"], [(0, 1), (1, 2)]), {"force": "nope"})


def test_unsorted_time_is_sorted(tmp_path):
    p = write_csv(tmp_path / "u.csv", ["t", "f_axial"], [(2, 2), (0, 0), (1, 1)])
    assert list(load(p)["t"]) == [0, 1, 2]


def test_inserted_run():
    m = analyze(synth("insert"))
    assert verdict(m) == "INSERTED" and m["jammed"] is False
    assert m["first_contact_t"] == pytest.approx(3.0, abs=0.02)
    assert m["insertion_t"] == pytest.approx(8.7, abs=0.05)         # depth 0.027 at 6 + 2.7 s
    assert m["time_to_insert_s"] == pytest.approx(5.7, abs=0.06)
    assert m["peak_force_n"] == pytest.approx(3.0)
    assert m["impulse_ns"] == pytest.approx(3.0 * 3.0, rel=0.05)       # 3 N for 3 s


def test_jam_run():
    m = analyze(synth("jam"))
    assert verdict(m) == "JAMMED"
    assert m["jam_t"] == pytest.approx(3.0, abs=0.1)
    assert m["peak_force_n"] == pytest.approx(20.0)
    assert m["steady_force_n"] == pytest.approx(20.0)
    assert m["overshoot_pct"] == pytest.approx(0.0, abs=1e-6)


def test_free_descent_force_is_not_contact():
    d = synth("insert")
    d["f_axial"] = d["force"] = np.where(d["t"] < 3, 1.0, d["force"])  # spring force while still 30 mm up
    # gate opens surface_tol (2 mm) above the surface: 2 mm at 10 mm/s is 0.2 s early, not 3 s early
    assert analyze(d)["first_contact_t"] == pytest.approx(2.8, abs=0.02)
    assert analyze(d, Params(surface_tol=1e-4))["first_contact_t"] == pytest.approx(2.99, abs=0.02)
    assert analyze(d, Params(surface_tol=None))["first_contact_t"] == pytest.approx(0.0, abs=0.02)


def test_no_depth_means_unknown_not_jammed():
    d = synth("jam")
    del d["depth"]
    m = analyze(d)
    assert m["jammed"] is None and m["inserted"] is None and verdict(m) == "NO DEPTH DATA"


def test_depth_from_z():
    d = synth("insert")
    d["z"] = 1.135 - d.pop("depth")
    m = analyze(d, Params(surface_z=1.135))
    assert m["inserted"] is True


def test_overshoot_and_settling():
    t = np.arange(0, 10, 0.01)
    f = np.where(t < 1, 0.0, 5.0 + 4.0 * np.exp(-(t - 1) * 3))      # lands at 9 N, settles to 5 N
    d = {"t": t, "f_axial": f, "force": f, "depth": np.zeros_like(t)}
    m = analyze(d)
    assert m["overshoot_pct"] == pytest.approx(80.0, rel=0.05)
    assert 0.5 < m["settling_time_s"] < 2.5


def test_never_touching():
    t = np.arange(0, 5, 0.01)
    d = {"t": t, "f_axial": np.zeros_like(t), "force": np.zeros_like(t), "depth": -0.03 + 0 * t}
    m = analyze(d)
    assert m["first_contact_t"] is None and m["impulse_ns"] == 0.0 and m["jammed"] is False


# regression on the real logs shipped in examples/data
@pytest.mark.parametrize("name,expected", [
    ("gazebo_ur3_off0.4mm_plain", "INSERTED"),
    ("gazebo_ur3_off4mm_plain", "JAMMED"),
    ("gazebo_ur3_off4mm_spiral", "INSERTED"),
    ("mujoco_ur3_off0.4mm_plain", "INSERTED"),
    ("mujoco_ur3_off1.5mm_plain", "JAMMED"),
    ("mujoco_ur3_off1.5mm_spiral", "INSERTED"),
    ("mujoco_ur3_off4mm_spiral", "JAMMED"),
])
def test_real_logs(name, expected):
    path = os.path.join(DATA, name + ".csv")
    if not os.path.exists(path):
        pytest.skip("example data missing")
    assert verdict(analyze(load(path))) == expected


def test_real_log_finds_the_wall_spike():
    path = os.path.join(DATA, "mujoco_ur3_off1.5mm_spiral.csv")
    if not os.path.exists(path):
        pytest.skip("example data missing")
    assert analyze(load(path))["peak_lateral_n"] > 100


def test_cli_analyze_json_and_plot(tmp_path, capsys):
    t = synth("insert")
    p = write_csv(tmp_path / "r.csv", ["t", "f_axial", "depth"], zip(t["t"], t["f_axial"], t["depth"]))
    assert main(["analyze", p, "--json", str(tmp_path / "m.json"), "--plot", str(tmp_path / "r.png")]) == 0
    assert "INSERTED" in capsys.readouterr().out
    assert json.load(open(tmp_path / "m.json"))["inserted"] is True
    assert (tmp_path / "r.png").stat().st_size > 1000


def test_cli_json_stdout_is_pure_json(tmp_path, capsys):
    p = write_csv(tmp_path / "r.csv", ["t", "f_axial"], [(0, 0), (1, 1), (2, 0)])
    assert main(["analyze", p, "--json", "-"]) == 0
    json.loads(capsys.readouterr().out)


def test_cli_compare(tmp_path, capsys):
    paths = []
    for k in ("insert", "jam"):
        s = synth(k)
        paths.append(write_csv(tmp_path / f"{k}.csv", ["t", "f_axial", "depth"], zip(s["t"], s["f_axial"], s["depth"])))
    assert main(["compare", *paths, "--out", str(tmp_path / "c.png"), "--logy"]) == 0
    out = capsys.readouterr().out
    assert "INSERTED" in out and "JAMMED" in out and (tmp_path / "c.png").exists()
    assert main(["compare", paths[0]]) == 2


def test_cli_bad_input_exits_2(tmp_path, capsys):
    assert main(["analyze", str(tmp_path / "missing.csv")]) == 2
    p = write_csv(tmp_path / "x.csv", ["a", "b"], [(1, 2), (2, 3)])
    assert main(["analyze", p]) == 2
    assert "forcetrace:" in capsys.readouterr().err
