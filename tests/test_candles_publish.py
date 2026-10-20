"""Candle publishing: mid OHLC CSVs incl. the forming candle, README/latest.json, nothing pushed without a key."""
import asyncio

from fxagents import candles_publish as cp


def c(t, o, h, l, cl, v, done=True):
    return {"time": t + ".000000000Z", "complete": done, "volume": v, "mid": {"o": o, "h": h, "l": l, "c": cl}}


class FakeClient:
    def __init__(self): self.calls = []

    async def req(self, method, path, params=None, **kw):
        self.calls.append((path, params["granularity"], params["price"]))
        return {"candles": [c("2026-10-20T20:00:00", "4100.1", "4101.0", "4099.5", "4100.8", 120),
                            c("2026-10-20T20:01:00", "4100.8", "4101.2", "4100.6", "4101.0", 30, done=False)]}


def test_csv_has_the_forming_candle_and_mid_prices():
    text, last = cp.to_csv(FakeClient_candles())
    rows = text.strip().split("\n")
    assert rows[0] == "time,open,high,low,close,volume,complete"
    assert rows[1] == "2026-10-20T20:00:00Z,4100.1,4101.0,4099.5,4100.8,120,true"
    assert rows[-1].endswith(",false") and last == "4101.0"


def FakeClient_candles():
    return asyncio.run(FakeClient().req("GET", "/x", params={"granularity": "M1", "price": "M"}))["candles"]


def test_refresh_writes_every_file_readme_and_latest(tmp_path):
    fc = FakeClient()
    info = asyncio.run(cp.refresh(tmp_path, fc, {"XAUUSD": "XAU_USD", "NDQ": "NAS100_USD"}))
    assert info["files"] == 2 * len(cp.GRANS)
    assert {p for _, _, p in fc.calls} == {"M"}                                                      # mid prices only
    assert (tmp_path / "XAUUSD_D.csv").exists() and (tmp_path / "NDQ_M5.csv").exists()
    r = (tmp_path / "README.md").read_text()
    assert "raw.githubusercontent.com" in r and "XAUUSD_H1.csv" in r and "MID price" in r
    assert "4101.0" in (tmp_path / "latest.json").read_text()


def test_nothing_is_pushed_without_the_deploy_key(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "KEY", tmp_path / "missing")
    assert cp.push(tmp_path).startswith("not pushed")


def test_push_keeps_one_commit_on_the_branch(tmp_path, monkeypatch):
    import subprocess
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    key = tmp_path / "key"; key.write_text("not a real key")
    out = tmp_path / "out"; out.mkdir()
    monkeypatch.setattr(cp, "KEY", key)
    monkeypatch.setenv("CANDLES_REMOTE", str(bare))
    for i in range(3):
        (out / "latest.json").write_text(f'{{"n": {i}}}')
        assert cp.push(out) == "pushed"
    n = subprocess.run(["git", "-C", str(bare), "rev-list", "--count", "candles"], capture_output=True, text=True).stdout.strip()
    shown = subprocess.run(["git", "-C", str(bare), "show", "candles:latest.json"], capture_output=True, text=True).stdout
    assert n == "1" and '"n": 2' in shown
