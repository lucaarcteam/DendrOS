import numpy as np
from typing import Optional
from scipy import stats as _stats
from .models.series import Series


def _common_years(a: Series, b: Series) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Align two series on common years and return their value arrays."""
    common = np.intersect1d(a.years, b.years)
    if len(common) < 2:
        return None
    idx_a = np.searchsorted(a.years, common)
    idx_b = np.searchsorted(b.years, common)
    return a.values[idx_a], b.values[idx_b]


def gleichlaeufigkeit(a: Series, b: Series) -> Optional[float]:
    """Gleichläufigkeit (GLK) — percentage of agreement in year-to-year changes."""
    common = _common_years(a, b)
    if common is None:
        return None
    va, vb = common
    if len(va) < 2:
        return None
    da = np.diff(va)
    db = np.diff(vb)
    same = np.sum((da > 0) & (db > 0)) + np.sum((da < 0) & (db < 0))
    return same / len(da) * 100.0


def pearson_r(a: Series, b: Series) -> Optional[float]:
    """Pearson correlation coefficient between two series on common years."""
    common = _common_years(a, b)
    if common is None:
        return None
    va, vb = common
    n = len(va)
    if n < 3:
        return None
    r = np.corrcoef(va, vb)[0, 1]
    return float(r)


def tvalue(r: float, n: int) -> Optional[float]:
    """Standard Student t-value from Pearson r and overlap n."""
    if n < 3 or abs(r) >= 1.0:
        return None
    return r * np.sqrt((n - 2) / (1 - r * r))


def pvalue_from_t(t: float, n: int) -> Optional[float]:
    """Two-tailed p-value from t-value and overlap n (df = n-2)."""
    if t is None or n < 3:
        return None
    df = n - 2
    if df < 1:
        return None
    return float(2 * (1 - _stats.t.cdf(abs(t), df)))


def tvalue_bp(r: float, n: int) -> Optional[float]:
    """Baillie-Pilcher t-value.
    n = overlap of BP-transformed series (already reduced by 4 from MA5).
    We subtract 2 for the correlation DF, giving total -6 from original.
    """
    adj = n - 2
    if adj < 1 or abs(r) >= 1.0:
        return None
    return r * np.sqrt(adj / (1 - r * r))


def bp_transform(series: Series) -> Optional[Series]:
    """Baillie-Pilcher pre-transform:
    5-year centered moving average + log(100 * value / ma).
    Returns series shortened by 2 years at each end.
    """
    vals = series.values
    if len(vals) < 5:
        return None
    ma5 = np.convolve(vals, np.ones(5) / 5, mode="valid")
    inner = vals[2:-2]
    transformed = np.log(100 * inner / ma5)
    mask = np.isfinite(transformed)
    if not np.any(mask):
        return None
    return Series(
        name=series.name,
        years=series.years[2:-2][mask],
        values=transformed[mask],
    )


def sliding_correlation(
    target: Series,
    reference: Series,
    min_overlap: int = 20,
    method: str = "bp",
) -> list[dict]:
    """Slide *target* against *reference* at all possible offsets.
    Returns list of dicts with offset, overlap, r, t, glk.
    Offset = reference.year - target.year for the first overlapping year.
    method: "pearson" (standard t) or "bp" (Baillie-Pilcher t, default).
    """
    if method == "bp":
        t_target = bp_transform(target)
        t_ref = bp_transform(reference)
        t_func = tvalue_bp
    else:
        t_target = target
        t_ref = reference
        t_func = tvalue

    if t_target is None or t_ref is None:
        return []

    results = []
    lo = t_ref.start_year - t_target.end_year
    hi = t_ref.end_year - t_target.start_year

    for offset in range(lo, hi + 1):
        shifted = Series(
            name=t_target.name,
            years=t_target.years + offset,
            values=t_target.values,
        )
        common = _common_years(shifted, t_ref)
        if common is None:
            continue
        va, vb = common
        n = len(va)
        if n < min_overlap:
            continue
        r = float(np.corrcoef(va, vb)[0, 1])
        t = t_func(r, n)
        p = pvalue_from_t(t, n)
        da = np.diff(va)
        db = np.diff(vb)
        same = np.sum((da > 0) & (db > 0)) + np.sum((da < 0) & (db < 0))
        glk = same / len(da) * 100.0 if len(da) > 0 else 0.0
        results.append({
            "offset": offset,
            "overlap": n,
            "r": r,
            "t": t,
            "p": p,
            "glk": glk,
        })

    results.sort(key=lambda x: x["t"] if x["t"] is not None else -1e9, reverse=True)
    return results


def build_master(series_list: list[Series], min_overlap: int = 2) -> Optional[Series]:
    """Build a master chronology by averaging overlapping series year by year."""
    if not series_list:
        return None

    year_map: dict[int, list[float]] = {}
    for s in series_list:
        for y, v in zip(s.years, s.values):
            year_map.setdefault(int(y), []).append(v)

    years = []
    values = []
    for y in sorted(year_map):
        vals = year_map[y]
        if len(vals) >= min_overlap:
            years.append(y)
            values.append(np.mean(vals))

    if not years:
        return None

    return Series(
        name="Master",
        years=np.array(years, dtype=int),
        values=np.array(values, dtype=float),
    )


def compute_pointer_years(
    series_list: list[Series],
    threshold: float = 75.0,
    min_series: int = 3,
) -> dict[int, str]:
    """Identify pointer years (Weiser years).

    For each year present in at least `min_series` series, compute the
    percentage of series that show a positive vs negative year-to-year change.
    If either percentage >= threshold, mark the year as "+" or "-".

    Returns dict mapping year -> sign ("+" or "-").
    """
    if not series_list:
        return {}

    year_changes: dict[int, list[float]] = {}
    for s in series_list:
        if len(s.values) < 2:
            continue
        diffs = np.diff(s.values)
        changes = np.where(diffs > 0, 1.0, -1.0)
        for y, c in zip(s.years[1:], changes):
            year_changes.setdefault(int(y), []).append(c)

    pointer = {}
    for y, changes in year_changes.items():
        if len(changes) < min_series:
            continue
        n_pos = sum(1 for c in changes if c > 0)
        n_neg = sum(1 for c in changes if c < 0)
        pct_pos = n_pos / len(changes) * 100
        pct_neg = n_neg / len(changes) * 100
        if pct_pos >= threshold:
            pointer[y] = "+"
        elif pct_neg >= threshold:
            pointer[y] = "-"

    return pointer
