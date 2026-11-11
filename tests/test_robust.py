import json
import os
import subprocess
import sys

import pytest

import forcetrace
from forcetrace.cli import dumps, main

DATA = os.path.join(os.path.dirname(__file__), "..", "examples", "data")
SPIRAL = os.path.join(DATA, "gazebo_ur3_off4mm_spiral.csv")


def csv_file(tmp_path, text, name="run.csv"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f"forcetrace {forcetrace.__version__}"


def test_python_dash_m_runs():
    r = subprocess.run([sys.executable, "-m", "forcetrace", "--version"], capture_output=True, text=True,
                       cwd=os.path.join(os.path.dirname(__file__), ".."))
    assert r.returncode == 0 and "forcetrace" in r.stdout


def test_json_is_strict_with_nan_input(tmp_path, capsys):
    p = csv_file(tmp_path, "t,f_axial\n0,0\n1,nan\n2,3\n3,1\n")
    assert main(["analyze", p, "--json", "-"]) == 0
    cap = capsys.readouterr()
    assert "NaN" not in cap.out and "Infinity" not in cap.out
    m = json.loads(cap.out, parse_constant=lambda c: pytest.fail(f"bare {c} in JSON"))
    assert m["samples"] == 3
    assert "dropped 1 row" in cap.err


def test_dumps_converts_numpy_and_nonfinite():
    import numpy as np
    out = dumps({"a": np.float64(1.5), "b": float("nan"), "c": np.int64(3), "d": [float("inf"), np.bool_(True)]})
    assert json.loads(out) == {"a": 1.5, "b": None, "c": 3, "d": [None, True]}
    assert out.endswith("\n")


def test_json_output_is_stable_between_runs(capsys):
    main(["analyze", SPIRAL, "--json", "-"])
    a = capsys.readouterr().out
    main(["analyze", SPIRAL, "--json", "-"])
    assert a == capsys.readouterr().out and a.endswith("}\n")


def test_compare_json_to_stdout_is_pure(capsys):
    other = os.path.join(DATA, "gazebo_ur3_off4mm_plain.csv")
    assert main(["compare", SPIRAL, other, "--json", "-"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert set(d) == {"gazebo_ur3_off4mm_spiral", "gazebo_ur3_off4mm_plain"}


def test_all_nan_file_is_an_error(tmp_path, capsys):
    p = csv_file(tmp_path, "t,f_axial\nnan,1\n0,nan\n")
    assert main(["analyze", p]) == 2
    assert "no finite data rows" in capsys.readouterr().err


@pytest.mark.parametrize("make,needle", [
    (lambda tp: str(tp / "missing.csv"), "file not found"),
    (lambda tp: str(tp), "is a directory"),
    (lambda tp: (tp / "b.csv").write_bytes(bytes(range(128, 256))) and None or str(tp / "b.csv"), "not a text CSV"),
])
def test_friendly_file_errors(tmp_path, capsys, make, needle):
    assert main(["analyze", make(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert needle in err and "Errno" not in err and "Traceback" not in err


def _csv(tmp_path, header, rows, name="run.csv"):
    p = tmp_path / name
    p.write_text(",".join(header) + "\n" + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n")
    return str(p)


def test_force_kind_labels_the_axis(tmp_path):
    from forcetrace.io import force_label, load
    path = _csv(tmp_path, ["t", "f_axial", "f_lateral"], [[0, 0, 0], [1, 1, 0], [2, 2, 0]])
    assert force_label(load(path)) == "force (N)"
    assert force_label(load(path, kind="commanded")) == "commanded force (N)"
    assert force_label(load(path, kind="simulated"), ", log scale") == "simulated contact force (N), log scale"


def test_bad_force_kind_is_rejected(tmp_path):
    import pytest
    from forcetrace.io import load
    path = _csv(tmp_path, ["t", "f_axial"], [[0, 0], [1, 1]])
    with pytest.raises(ValueError, match="force kind"):
        load(path, kind="guessed")


def test_measured_columns_win_unless_commanded_is_asked_for(tmp_path):
    from forcetrace.io import load
    path = _csv(tmp_path, ["t", "f_axial", "f_lateral", "f_meas_axial", "f_meas_lateral"],
                [[0, 5, 0, 1, 0], [1, 6, 0, 2, 0], [2, 7, 0, 3, 0]])
    d = load(path)
    assert d["_kind"] == "measured" and list(d["f_axial"]) == [1, 2, 3] and list(d["f_cmd"]) == [5, 6, 7]
    assert "f_meas_axial" not in d
    c = load(path, kind="commanded")
    assert c["_kind"] == "commanded" and list(c["f_axial"]) == [5, 6, 7] and "f_cmd" not in c
