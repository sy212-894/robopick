import numpy as np

from curation_tools.rule_check import check

LEVELS = ("worse", "okay", "better")


def _demos(n=120, sign=1.0, labels=True, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        q = LEVELS[i % 3]
        base = (2 - LEVELS.index(q)) * sign  # sign=1: 서툰 시범일수록 신호가 큼 (규칙과 맞음)
        d = {"id": f"demo_{i}", "split": "train", "length": 100 + 40 * base + rng.normal(0, 10),
             "idle_ratio": 0.1 + 0.02 * base + rng.normal(0, 0.01), "path_length": 1 + 0.2 * base + rng.normal(0, 0.05),
             "gripper_switches": 2 + base + rng.integers(0, 2)}
        if labels:
            d["quality"] = q
        out.append(d)
    return out


def test_pass_when_rule_matches_labels():
    r = check(_demos())
    assert r["verdict"] == "통과" and r["ci95"][1] < 0
    assert r["halves"]["top"]["better"] > r["halves"]["bottom"]["better"]
    assert len(r["signals"]) == 4


def test_reverse_when_rule_is_backwards():
    assert check(_demos(sign=-1.0))["verdict"] == "반대"


def test_unclear_without_relation():
    assert check(_demos(sign=0.0, seed=1))["verdict"] == "불분명"


def test_no_labels():
    r = check(_demos(labels=False))
    assert r["status"] == "no_labels" and r["verdict"] == "점검 불가"


def test_reproducible():
    assert check(_demos()) == check(_demos())
