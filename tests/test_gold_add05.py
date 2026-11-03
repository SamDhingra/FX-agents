"""Gold add-on-resume at +0.5R: vault-only, judged once."""
import numpy as np
import pytest

from fxagents import gold_add05 as G
from tests.test_breakout import frame


def test_runs_once_on_the_vault(tmp_path):
    rng = np.random.default_rng(9)
    px = 1200 + np.cumsum(rng.normal(0, 0.6, 1440 * 15))
    m1 = frame(px, start="2017-03-05 21:00", spread=0.3)
    m1 = m1[m1.index.dayofweek < 5]
    j = G.run(out=tmp_path / "v", m1=m1)
    assert "gates" in j and (tmp_path / "v" / "report.md").read_text().startswith("# Gold breakout: add")
    with pytest.raises(SystemExit, match="judged once"):
        G.run(out=tmp_path / "v", m1=m1)
