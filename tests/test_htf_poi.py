"""Sam's HTF point-of-interest models (fxagents/bt/htf_poi.py + btplugins/htf_*.py): FVG and CISD pieces, targets at
least 1R away on untaken liquidity, both entries, and no look-ahead."""
import numpy as np
import pandas as pd
import pytest

from fxagents.bt import data, engine
from fxagents.bt import htf_poi as hp
from fxagents.bt.run import code_sha, load_plugin
from tests.test_gemini_smc import frame, walk

PLUGINS = ["htf_a_4h_fvg_m15_mss", "htf_b_daily_h1_cisd", "htf_c_h1_sweep_fvg"]


@pytest.fixture(scope="module")
def m():
    return data.from_frame(frame(walk(seed=7, n_days=120)), symbol="NDQ")


def test_fvg_and_cisd_pieces():
    b = pd.DataFrame({"h": [10, 11, 14, 15.0], "l": [9, 10, 12, 13.5]})
    atr = np.full(4, 1.0)
    assert hp.fvg_at(b, atr, 2, 1) == (10, 12)                   # low[2]=12 > high[0]=10
    assert hp.fvg_at(b, atr, 2, -1) is None
    assert [x[:2] for x in hp.fvgs(b, atr)] == [(2, 1), (3, 1)]
    o = np.array([10, 11, 10.5, 10.0, 9.5]); c = np.array([11, 10.5, 10.0, 9.5, 10.6])
    assert hp.cisd_level(o, c, 3, 1, 0) == 11.0                  # down-closes at 1,2,3 → open of candle 1


@pytest.mark.parametrize("plugin", PLUGINS)
@pytest.mark.parametrize("entry", ["market", "limit_mid"])
def test_models_run_without_look_ahead(m, plugin, entry):
    cls, _ = load_plugin(f"btplugins/{plugin}.py")
    s = cls(entry=entry)
    sig = s.signals(m)
    assert sig, "the synthetic market should produce some setups"
    for x in sig:
        ref = x.price if entry == "limit_mid" else None
        if ref is not None:
            assert x.entry == "limit" and x.cancel == x.target
            assert (x.target - ref) * x.side >= (ref - x.stop) * x.side - 1e-9     # target ≥ 1R from the limit
        assert x.info["target_r"] >= 1.0 - 1e-9
    a = engine.lookahead_audit(s, m, sig, 6, warm_days=60)
    assert a["failed"] == 0, a["examples"]
    engine.simulate(s, m)


def test_fingerprint_covers_the_shared_rules(tmp_path, monkeypatch):
    src = open("btplugins/htf_b_daily_h1_cisd.py", "rb").read()
    a = code_sha(src)
    import fxagents.bt.run as run
    fake = tmp_path / "fxagents"; (fake / "bt").mkdir(parents=True)
    for f in ("bt/htf_poi.py", "liquidity.py", "bt/ind.py", "bias.py"):
        (fake / f).write_bytes((run.PKG / f).read_bytes())
    (fake / "bt/htf_poi.py").write_bytes((run.PKG / "bt/htf_poi.py").read_bytes() + b"\n# changed\n")
    monkeypatch.setattr(run, "PKG", fake)
    assert code_sha(src) != a
