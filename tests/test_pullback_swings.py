import numpy as np

from fxagents.structure import pivots_pullback


def _series(n=600, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.random(n)
    l = np.minimum(o, c) - rng.random(n)
    return h, l, c


def test_pullback_swings_alternate_and_need_a_validating_close():
    h, l, c = _series()
    piv = pivots_pullback(h, l, c)
    assert len(piv) > 10
    assert all(a.kind != b.kind for a, b in zip(piv, piv[1:]))
    for p in piv:
        assert p.known_at > p.idx
        if p.kind == "H":
            assert c[p.known_at] < l[p.idx] and h[p.idx] == h[p.idx:p.known_at + 1].max()
        else:
            assert c[p.known_at] > h[p.idx] and l[p.idx] == l[p.idx:p.known_at + 1].min()


def test_pullback_swings_are_causal():
    h, l, c = _series()
    full = pivots_pullback(h, l, c)
    for cut in (150, 300, 451):
        part = pivots_pullback(h[:cut], l[:cut], c[:cut])
        assert part == [p for p in full if p.known_at < cut]
