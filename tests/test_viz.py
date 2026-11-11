import json
import os
import re

import numpy as np
import pytest

from forcetrace.cli import main
from forcetrace.dashboard import build_payload, write_dashboard
from forcetrace.io import load
from forcetrace.metrics import analyze
from forcetrace.viz import force_norm, local_xy, need_xy

DATA = os.path.join(os.path.dirname(__file__), "..", "examples", "data")
GZ = os.path.join(DATA, "gazebo_ur3_off4mm_spiral.csv")
MJ = os.path.join(DATA, "mujoco_ur3_off2.5mm_spiral.csv")


@pytest.fixture
def noxy(tmp_path):
    p = tmp_path / "noxy.csv"
    p.write_text("t,f_axial,depth\n" + "\n".join(f"{i * 0.1:.1f},{3 if i > 5 else 0},{-0.03 + 0.005 * i}" for i in range(20)) + "\n")
    return str(p)


def run(path):
    d = load(path)
    return os.path.basename(path), d, analyze(d)


def test_loader_reads_xy_aliases(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("t,tip_x,pos_y,f\n0,1.0,2.0,0.5\n1,1.1,2.1,0.6\n")
    d = load(str(p))
    assert np.allclose(d["x"], [1.0, 1.1]) and np.allclose(d["y"], [2.0, 2.1])


def test_local_xy_relative_to_hole_in_mm():
    d = {"x": np.array([0.281, 0.2825]), "y": np.array([0.14, 0.1405])}
    X, Y = local_xy(d, (0.28, 0.14))
    assert np.allclose(X, [1.0, 2.5]) and np.allclose(Y, [0.0, 0.5])
    X0, Y0 = local_xy(d, None)                      # no hole: relative to the first sample
    assert X0[0] == 0 and Y0[0] == 0


def test_need_xy_message():
    with pytest.raises(ValueError, match="x/y"):
        need_xy({"t": [0], "force": [0]})


def test_force_norm_ignores_a_single_spike():
    f = np.concatenate([np.full(1000, 3.0), [230.0]])
    assert force_norm(f).vmax < 10
    assert force_norm(np.zeros(5)).vmax == 2.0       # never a degenerate scale


def test_payload_thins_and_has_cards():
    runs = [run(GZ), run(MJ)]
    pl = build_payload(runs, hole=(0.28, 0.14), half=0.0005, max_points=100)
    assert len(pl["runs"]) == 2 and pl["zone_half_mm"] == 0.5
    r = pl["runs"][0]
    assert len(r["t"]) == len(r["force"]) == len(r["x"]) == len(r["depth"]) <= 100
    assert r["verdict"] == "INSERTED" and any(c[0] == "peak force" for c in r["cards"])
    json.dumps(pl, allow_nan=False)                   # no NaN/inf may leak into the page


def test_payload_without_xy_or_hole(noxy):
    pl = build_payload([run(noxy)], hole=None)
    assert "x" not in pl["runs"][0] and pl["zone_half_mm"] is None


def test_dashboard_is_self_contained(tmp_path):
    out = tmp_path / "d.html"
    write_dashboard([run(GZ), run(MJ)], str(out), hole=(0.28, 0.14), title="a <b> & c")
    html = out.read_text()
    assert html.startswith("<!doctype html>") and "&lt;b>" in html
    urls = set(re.findall(r"https?://[^\"'\s)]+", html))
    assert urls <= {"http://www.w3.org/2000/svg"}     # no CDN, no external requests
    blob = re.search(r"const D=(\{.*?\}),COL=", html, re.S).group(1)
    assert len(json.loads(blob)["runs"]) == 2


def test_cli_dashboard_and_errors(tmp_path, capsys, noxy):
    out = tmp_path / "d.html"
    assert main(["dashboard", GZ, MJ, "--hole", "0.28", "0.14", "--out", str(out)]) == 0
    assert out.stat().st_size > 5000
    assert main(["map", noxy, "--out", str(tmp_path / "m.png")]) == 2
    assert "x/y" in capsys.readouterr().err


def test_cli_map_and_animate_smoke(tmp_path):
    png, gif = tmp_path / "m.png", tmp_path / "a.gif"
    assert main(["map", GZ, "--hole", "0.28", "0.14", "--out", str(png)]) == 0
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert main(["animate", GZ, "--hole", "0.28", "0.14", "--out", str(gif), "--fps", "4", "--seconds", "1"]) == 0
    assert gif.read_bytes()[:6] == b"GIF89a"
