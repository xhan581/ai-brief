"""Pull the numbers for the weekly AI build-out brief.

Writes:
  data/latest.json  - every series, machine-readable (the renderer reads this)
  data/summary.md   - the same numbers as compact tables (the agent reads this)

Every number the brief states about these series must come from here, so this
file is deliberately boring: download, clean, compute, write. No opinions.

Sources (all free, no keys):
  SEC XBRL company facts  - capex, operating cash flow, leases, debt, revenue
  FRED                    - credit spreads, rates, GDP contributions, power
  Yahoo Finance chart API - ETF / stock prices (best effort; can rate-limit)

Env vars:
  SEC_USER_AGENT   SEC asks for "name email" in the User-Agent. Set it to yours.
  RAW_CACHE_DIR    optional folder of pre-downloaded responses (see raw_get).
  OFFLINE=1        only use RAW_CACHE_DIR, never touch the network.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = Path(os.environ["RAW_CACHE_DIR"]) if os.environ.get("RAW_CACHE_DIR") else None
OFFLINE = os.environ.get("OFFLINE") == "1"
SEC_UA = os.environ.get("SEC_USER_AGENT") or "ai-brief research contact@example.com"
TODAY = dt.date.today()

# ---------------------------------------------------------------------------
# What we track
# ---------------------------------------------------------------------------

HYPERSCALERS = {  # the spenders
    "MSFT": "0000789019",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "ORCL": "0001341439",
}
SUPPLIERS = {  # who receives the money
    "NVDA": "0001045810",
    "AVGO": "0001730168",
    "AMD": "0000002488",
    "MU": "0000723125",
    "VRT": "0001674101",
}

# XBRL tags, in order of preference. The tag with the most recent data wins.
TAGS = {
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
    ],
    "ocf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    # New finance leases are non-cash, so they never show up in capex even
    # though they are the same data-center spend financed a different way.
    "lease_adds": ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"],
    "debt_proceeds": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfDebt",
        "ProceedsFromIssuanceOfUnsecuredDebt",
    ],
    "debt_repay": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfSeniorDebt",
        "RepaymentsOfDebt",
    ],
    # Balance-sheet (instant) value: long-term debt, non-current portion.
    # Same concept for all five; excludes commercial paper and current maturities.
    "debt_lt": [
        "LongTermDebtNoncurrent",
        "LongTermNotesAndLoans",  # Oracle's tag
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
}
INSTANT_FIELDS = {"debt_lt"}
HYPERSCALER_FIELDS = ["capex", "ocf", "lease_adds", "debt_proceeds", "debt_repay", "debt_lt"]
SUPPLIER_FIELDS = ["revenue"]

FRED_DAILY = {
    "ig_oas": ("BAMLC0A0CM", "IG corporate OAS (ICE BofA)", "%"),
    "bbb_oas": ("BAMLC0A4CBBB", "BBB OAS (ICE BofA)", "%"),
    "hy_oas": ("BAMLH0A0HYM2", "HY OAS (ICE BofA)", "%"),
    "ust10": ("DGS10", "10y Treasury yield", "%"),
    "ust2": ("DGS2", "2y Treasury yield", "%"),
    "tp10": ("THREEFYTP10", "10y term premium (Kim-Wright)", "%"),
    "spx": ("SP500", "S&P 500 index", "index"),
    "ndx": ("NASDAQ100", "Nasdaq-100 index", "index"),
}
FRED_QUARTERLY = {
    "gdp_growth": ("A191RL1Q225SBEA", "Real GDP growth, % SAAR", "%"),
    "contrib_ipe": ("Y034RY2Q224SBEA", "Contribution to GDP growth: information processing equipment", "pp"),
    "contrib_software": ("B985RY2Q224SBEA", "Contribution to GDP growth: software", "pp"),
    "productivity": ("OPHNFB", "Nonfarm business output per hour (index)", "index"),
}
FRED_MONTHLY = {
    "cpi_electricity": ("CUSR0000SEHF01", "CPI: electricity (index)", "index"),
    "power_construction": ("TLPWRCONS", "Construction spending: power, $mn SAAR", "$mn"),
}

YAHOO = ["SPY", "RSP", "SMH", "XLU", "QQQ", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "ORCL", "CRWV"]

# ---------------------------------------------------------------------------
# Download layer
# ---------------------------------------------------------------------------


def cache_name(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:20]


def raw_get(url: str, headers: dict | None = None, retries: int = 3) -> bytes:
    """GET a URL. If RAW_CACHE_DIR holds a pre-downloaded copy, use that instead.

    The cache exists so the pipeline can be tested on a machine that can't reach
    these sites directly: download the responses some other way, save each one
    as RAW_CACHE_DIR/<cache_name(url)>, and run with OFFLINE=1.
    """
    if RAW_DIR is not None:
        p = RAW_DIR / cache_name(url)
        if p.exists():
            return p.read_bytes()
    if OFFLINE:
        raise RuntimeError(f"offline and not cached: {url}")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            if RAW_DIR is not None:
                RAW_DIR.mkdir(parents=True, exist_ok=True)
                (RAW_DIR / cache_name(url)).write_bytes(body)
            return body
        except Exception as e:  # noqa: BLE001 - we report, not crash
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def sec_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def fred_url(series: str, start: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"


def yahoo_url(symbol: str) -> str:
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3y&interval=1d&events=history"


# ---------------------------------------------------------------------------
# SEC: turn XBRL facts into clean calendar quarters
# ---------------------------------------------------------------------------


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def cal_quarter(start: dt.date, end: dt.date) -> str:
    """Label a fiscal quarter by the calendar quarter holding its midpoint.

    Works for odd fiscal calendars: NVDA's quarter ending late January is
    labelled Q4 of the prior year, Oracle's ending August 31 is Q3.
    """
    mid = start + (end - start) / 2
    return f"{mid.year}Q{(mid.month - 1) // 3 + 1}"


def tag_rows(facts: dict, tag: str) -> list[dict]:
    rows = facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
    return [r for r in rows if isinstance(r.get("val"), (int, float)) and r.get("form") in ("10-Q", "10-K", "10-Q/A", "10-K/A")]


def merged_flow_rows(facts: dict, candidates: list[str]) -> tuple[list[str], list[dict]]:
    """Flow items (cash flow, revenue): companies sometimes switch tag names for the
    same line. For each period, take the rows of the first candidate tag that has
    that period, so a tag switch doesn't punch holes in the history."""
    chosen: dict[tuple, str] = {}
    by_tag = {t: tag_rows(facts, t) for t in candidates}
    for t in candidates:
        for r in by_tag[t]:
            chosen.setdefault((r.get("start"), r["end"]), t)
    rows = [r for t in candidates for r in by_tag[t] if chosen[(r.get("start"), r["end"])] == t]
    used = [t for t in candidates if t in set(chosen.values())]
    return used, rows


def best_instant_tag(facts: dict, candidates: list[str]) -> tuple[str | None, list[dict]]:
    """Balance-sheet items: pick ONE tag (mixing concepts creates fake jumps) -
    the one with the most distinct period-ends in the last ~2 years."""
    cutoff = (TODAY - dt.timedelta(days=800)).isoformat()
    best, best_n = (None, []), 0
    for t in candidates:
        rows = [r for r in tag_rows(facts, t) if not r.get("start")]
        n = len({r["end"] for r in rows if r["end"] >= cutoff})
        if n > best_n:
            best, best_n = (t, rows), n
    return best


def dedupe_latest(rows: list[dict], key) -> dict:
    """Keep the most recently filed value for each period (captures restatements)."""
    out = {}
    for r in sorted(rows, key=lambda r: r.get("filed", "")):
        out[key(r)] = r
    return out


def quarterize(rows: list[dict]) -> dict[str, dict]:
    """Discrete quarterly values from a mix of 3-month, year-to-date and annual facts.

    Cash-flow items are only reported year-to-date (6M, 9M, 12M), so a quarter
    is YTD(start, end) minus YTD(start, previous quarter end). Income-statement
    items usually report the 3-month value directly, which we prefer.
    """
    by_period = dedupe_latest([r for r in rows if r.get("start")], lambda r: (r["start"], r["end"]))
    vals = {(d(s), d(e)): float(r["val"]) for (s, e), r in by_period.items()}
    quarters: dict[tuple[dt.date, dt.date], float] = {}
    for (s, e), v in vals.items():
        if 80 <= (e - s).days <= 100:
            quarters[(s, e)] = v
    for (s, e), v in vals.items():
        if (e - s).days <= 100:
            continue
        for (s2, p), v2 in vals.items():
            if s2 == s and p < e and 80 <= (e - p).days <= 100:
                qs = p + dt.timedelta(days=1)
                if not any(abs((qe - e).days) <= 3 for (_, qe) in quarters):
                    quarters[(qs, e)] = v - v2
    out = {}
    for (s, e), v in sorted(quarters.items(), key=lambda kv: kv[0][1]):
        out[cal_quarter(s, e)] = {"value": v, "period_end": e.isoformat()}
    return out


def instants(rows: list[dict]) -> dict[str, dict]:
    by_end = dedupe_latest([r for r in rows if not r.get("start")], lambda r: r["end"])
    out = {}
    for e, r in sorted(by_end.items()):
        ed = d(e)
        out[cal_quarter(ed - dt.timedelta(days=89), ed)] = {"value": float(r["val"]), "period_end": e}
    return out


def sec_company(ticker: str, cik: str, fields: list[str]) -> dict:
    facts = json.loads(raw_get(sec_url(cik), {"User-Agent": SEC_UA, "Accept": "application/json"}))
    result = {"ticker": ticker, "entity": facts.get("entityName"), "fields": {}, "tags": {}}
    for f in fields:
        if f in INSTANT_FIELDS:
            tag, rows = best_instant_tag(facts, TAGS[f])
            result["tags"][f] = tag
            result["fields"][f] = instants(rows) if tag else {}
        else:
            used, rows = merged_flow_rows(facts, TAGS[f])
            result["tags"][f] = "+".join(used) if used else None
            result["fields"][f] = quarterize(rows) if rows else {}
    return result


# ---------------------------------------------------------------------------
# FRED and Yahoo
# ---------------------------------------------------------------------------


def fred_series(series: str, start: str) -> list[list]:
    text = raw_get(fred_url(series, start)).decode()
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or not rows[0] or "observation_date" not in rows[0][0]:
        raise RuntimeError(f"FRED {series}: unexpected response")
    out = []
    for date, val in rows[1:]:
        try:
            out.append([date, float(val)])
        except ValueError:
            pass  # FRED marks holidays with "."
    if not out:
        raise RuntimeError(f"FRED {series}: no observations")
    return out


def yahoo_series(symbol: str) -> list[list]:
    j = json.loads(raw_get(yahoo_url(symbol), {"User-Agent": "Mozilla/5.0"}))
    res = j["chart"]["result"][0]
    ts = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    out = []
    for t, c in zip(ts, closes):
        if c is not None:
            out.append([dt.datetime.utcfromtimestamp(t).date().isoformat(), float(c)])
    if len(out) < 20:
        raise RuntimeError(f"Yahoo {symbol}: too few observations")
    return out


# ---------------------------------------------------------------------------
# Small helpers for derived numbers
# ---------------------------------------------------------------------------


def value_on_or_before(series: list[list], date: dt.date):
    best = None
    for dstr, v in series:
        if d(dstr) <= date:
            best = v
        else:
            break
    return best


def qkey_shift(q: str, n: int) -> str:
    y, k = int(q[:4]), int(q[-1])
    idx = y * 4 + (k - 1) + n
    return f"{idx // 4}Q{idx % 4 + 1}"


def fmt_bn(x):
    return "n/a" if x is None else f"{x / 1e9:,.1f}"


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a / b - 1) * 100


def fmt_pct(x, signed=True):
    if x is None:
        return "n/a"
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------


def build() -> dict:
    status: dict[str, str] = {}
    out: dict = {"generated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "status": status}

    # --- SEC ---
    companies = {}
    for group, names, fields in (("hyperscalers", HYPERSCALERS, HYPERSCALER_FIELDS), ("suppliers", SUPPLIERS, SUPPLIER_FIELDS)):
        for t, cik in names.items():
            try:
                companies[t] = sec_company(t, cik, fields) | {"group": group}
                status[f"sec:{t}"] = "ok"
            except Exception as e:  # noqa: BLE001
                status[f"sec:{t}"] = f"FAILED: {e}"
            time.sleep(0.2)  # SEC asks for <10 requests/second
    out["companies"] = companies

    # Per-company derived quarterly table
    for t, c in companies.items():
        f = c["fields"]
        qs = sorted(set().union(*[set(v) for v in f.values()]) if f else set())
        rows = {}
        for q in qs:
            g = lambda k: f.get(k, {}).get(q, {}).get("value")  # noqa: E731
            row = {k: g(k) for k in f}
            row["period_end"] = next((f[k][q]["period_end"] for k in f if q in f.get(k, {})), None)
            if c["group"] == "hyperscalers":
                if row.get("capex") is not None:
                    row["capex"] = abs(row["capex"])
                if row.get("ocf") is not None and row.get("capex") is not None:
                    row["fcf"] = row["ocf"] - row["capex"]
                if row.get("debt_proceeds") is not None:
                    row["net_debt_issuance"] = row["debt_proceeds"] - abs(row.get("debt_repay") or 0)
            rows[q] = row
        c["quarters"] = rows

    # Hyperscaler aggregate by calendar quarter (only quarters where all report)
    agg = {}
    hs = [t for t in HYPERSCALERS if t in companies]
    all_q = sorted(set().union(*[set(companies[t]["quarters"]) for t in hs])) if hs else []
    for q in all_q:
        rows = [companies[t]["quarters"].get(q, {}) for t in hs]
        if len(hs) == len(HYPERSCALERS) and all(r.get("capex") is not None and r.get("ocf") is not None for r in rows):
            agg[q] = {
                "capex": sum(r["capex"] for r in rows),
                "ocf": sum(r["ocf"] for r in rows),
                "lease_adds": sum(r.get("lease_adds") or 0 for r in rows),
                "debt_lt": sum(r["debt_lt"] for r in rows) if all(r.get("debt_lt") is not None for r in rows) else None,
                "by_company": {t: companies[t]["quarters"][q]["capex"] for t in hs},
            }
    for q, a in agg.items():
        prev4 = [agg.get(qkey_shift(q, -i)) for i in range(4)]
        if all(prev4):
            a["capex_t4q"] = sum(p["capex"] for p in prev4)
            a["ocf_t4q"] = sum(p["ocf"] for p in prev4)
            a["lease_adds_t4q"] = sum(p["lease_adds"] for p in prev4)
            a["capex_to_ocf_t4q"] = a["capex_t4q"] / a["ocf_t4q"]
        y = agg.get(qkey_shift(q, -4))
        a["capex_yoy"] = pct(a["capex"], y["capex"]) if y else None
    out["hyperscaler_aggregate"] = agg

    # --- FRED ---
    start_daily = (TODAY - dt.timedelta(days=3 * 366)).isoformat()
    start_slow = "2018-01-01"
    fred = {}
    for group, start in ((FRED_DAILY, start_daily), (FRED_QUARTERLY, start_slow), (FRED_MONTHLY, start_slow)):
        for key, (sid, label, unit) in group.items():
            try:
                fred[key] = {"id": sid, "label": label, "unit": unit, "obs": fred_series(sid, start)}
                status[f"fred:{sid}"] = "ok"
            except Exception as e:  # noqa: BLE001
                status[f"fred:{sid}"] = f"FAILED: {e}"
    out["fred"] = fred

    # --- Yahoo ---
    prices = {}
    for s in YAHOO:
        try:
            prices[s] = yahoo_series(s)
            status[f"yahoo:{s}"] = "ok"
        except Exception as e:  # noqa: BLE001
            status[f"yahoo:{s}"] = f"FAILED: {e}"
        time.sleep(0.3)
    out["prices"] = prices

    # Relative-performance ratios, indexed to 100 one year ago
    ratios = {}
    def ratio(num: list[list], den: list[list]) -> list[list]:
        dmap = dict((a, b) for a, b in den)
        return [[a, b / dmap[a]] for a, b in num if a in dmap]
    if "SPY" in prices:
        pairs = {"SMH/SPY": "SMH", "RSP/SPY": "RSP", "XLU/SPY": "XLU"}
        for name, sym in pairs.items():
            if sym in prices:
                ratios[name] = ratio(prices[sym], prices["SPY"])
        basket = [s for s in ("MSFT", "AMZN", "GOOGL", "META", "ORCL") if s in prices]
        if len(basket) == 5:
            dates = sorted(set.intersection(*[set(x[0] for x in prices[s]) for s in basket]))
            maps = {s: dict(prices[s]) for s in basket}
            base = dates[0]
            ew = [[dd, sum(maps[s][dd] / maps[s][base] for s in basket) / 5] for dd in dates]
            ratios["Hyperscalers/SPY"] = ratio(ew, prices["SPY"])
    for name, series in ratios.items():
        last = d(series[-1][0])
        b = value_on_or_before(series, last - dt.timedelta(days=365))
        if b:
            ratios[name] = [[a, 100 * v / b] for a, v in series if d(a) >= last - dt.timedelta(days=365)]
    out["ratios"] = ratios
    return out


# ---------------------------------------------------------------------------
# Human/agent-readable summary
# ---------------------------------------------------------------------------


def changes_line(series: list[list], unit: str) -> str:
    last_d, last_v = d(series[-1][0]), series[-1][1]
    cells = []
    for label, days in (("1w", 7), ("1m", 30), ("3m", 91), ("1y", 365)):
        v = value_on_or_before(series, last_d - dt.timedelta(days=days))
        if v is None:
            cells.append("n/a")
        elif unit == "%":
            cells.append(f"{(last_v - v) * 100:+.0f}bp")
        else:
            cells.append(fmt_pct(pct(last_v, v)))
    return " | ".join(cells)


def summary_md(data: dict) -> str:
    L = []
    w = L.append
    w(f"# Data summary — generated {data['generated_at']}")
    w("")
    w("All figures below come straight from the sources named. $ figures are US$ billions unless marked.")
    w("Quarters are CALENDAR quarters (fiscal quarters are mapped by their midpoint).")
    w("")

    # Spend + funding
    agg = data.get("hyperscaler_aggregate", {})
    comps = data.get("companies", {})
    w("## 1. Spend and funding — hyperscalers (MSFT, AMZN, GOOGL, META, ORCL)")
    w("Source: SEC 10-Q/10-K XBRL (cash-flow statement). Aggregate shown only for quarters where all five have reported.")
    w("")
    w("| Quarter | Capex $bn | Capex YoY | New finance leases $bn | OCF $bn | T4Q capex $bn | T4Q OCF $bn | T4Q capex/OCF | LT debt, non-current, combined $bn |")
    w("|---|---|---|---|---|---|---|---|---|")
    for q in list(agg)[-10:]:
        a = agg[q]
        r = a.get("capex_to_ocf_t4q")
        w(f"| {q} | {fmt_bn(a['capex'])} | {fmt_pct(a.get('capex_yoy'))} | {fmt_bn(a['lease_adds'])} | {fmt_bn(a['ocf'])} | "
          f"{fmt_bn(a.get('capex_t4q'))} | {fmt_bn(a.get('ocf_t4q'))} | {'n/a' if r is None else f'{r:.0%}'} | {fmt_bn(a.get('debt_lt'))} |")
    w("")
    w("### Per company, last 6 reported quarters ($bn)")
    for t in HYPERSCALERS:
        c = comps.get(t)
        if not c:
            w(f"- {t}: DATA MISSING")
            continue
        w("")
        w(f"**{t}** (tags: capex={c['tags'].get('capex')}, debt proceeds={c['tags'].get('debt_proceeds')}, LT debt={c['tags'].get('debt_lt')})")
        w("")
        w("| Quarter | Period end | Capex | OCF | FCF | New fin. leases | Debt proceeds | Debt repaid | LT debt, non-current (end) |")
        w("|---|---|---|---|---|---|---|---|---|")
        for q in list(c["quarters"])[-6:]:
            r = c["quarters"][q]
            w(f"| {q} | {r.get('period_end')} | {fmt_bn(r.get('capex'))} | {fmt_bn(r.get('ocf'))} | {fmt_bn(r.get('fcf'))} | "
              f"{fmt_bn(r.get('lease_adds'))} | {fmt_bn(r.get('debt_proceeds'))} | {fmt_bn(abs(r['debt_repay']) if r.get('debt_repay') is not None else None)} | "
              f"{fmt_bn(r.get('debt_lt'))} |")
    w("")
    w("Notes: 'Debt proceeds' is gross long-term issuance as reported (tag differs by company); 'n/a' usually means the company reported no such line that quarter. "
      "'LT debt, non-current' is the balance-sheet figure at quarter end and excludes commercial paper and current maturities. "
      "New finance leases are non-cash and are NOT in capex; they are extra spend financed by lessors.")
    w("")

    # Receivers
    w("## 2. Receivers — supplier revenue")
    w("Source: SEC 10-Q/10-K XBRL (income statement).")
    w("")
    w("| Company | " + " | ".join(["Q-5", "Q-4", "Q-3", "Q-2", "Q-1", "Latest"]) + " |")
    w("|---|---|---|---|---|---|---|")
    for t in SUPPLIERS:
        c = comps.get(t)
        if not c:
            w(f"| {t} | DATA MISSING |||||| ")
            continue
        qs = list(c["quarters"])[-6:]
        cells = []
        for q in qs:
            v = c["quarters"][q].get("revenue")
            y = c["quarters"].get(qkey_shift(q, -4), {}).get("revenue")
            cells.append(f"{q}: {fmt_bn(v)} ({fmt_pct(pct(v, y))} YoY)")
        w(f"| {t} | " + " | ".join(cells) + " |")
    w("")

    # Credit / rates
    fred = data.get("fred", {})
    w("## 3. Credit and rates (daily)")
    w("Source: FRED (ICE BofA indices, Treasury, Kim-Wright term premium). Changes in bp.")
    w("")
    w("| Series | Latest | As of | Δ1w | Δ1m | Δ3m | Δ1y |")
    w("|---|---|---|---|---|---|---|")
    for k in ("ig_oas", "bbb_oas", "hy_oas", "ust2", "ust10", "tp10"):
        s = fred.get(k)
        if not s:
            w(f"| {k} | MISSING |||||")
            continue
        w(f"| {s['label']} | {s['obs'][-1][1]:.2f}% | {s['obs'][-1][0]} | {changes_line(s['obs'], '%')} |")
    w("")

    # Macro
    w("## 4. Macro (quarterly / monthly)")
    w("Source: BEA and BLS via FRED; Census construction spending via FRED.")
    w("")
    gq = {o[0]: o[1] for o in fred.get("gdp_growth", {}).get("obs", [])}
    ci = {o[0]: o[1] for o in fred.get("contrib_ipe", {}).get("obs", [])}
    cs = {o[0]: o[1] for o in fred.get("contrib_software", {}).get("obs", [])}
    w("| Quarter start | Real GDP growth % SAAR | Contribution: info-processing equipment (pp) | Contribution: software (pp) | IT equip + software share of growth |")
    w("|---|---|---|---|---|")
    for q in sorted(gq)[-8:]:
        tot = (ci.get(q) or 0) + (cs.get(q) or 0)
        share = f"{tot / gq[q]:.0%}" if gq[q] > 0 else "n/a (GDP growth ≤ 0)"
        w(f"| {q} | {gq[q]:.1f} | {ci.get(q, 'n/a')} | {cs.get(q, 'n/a')} | {share} |")
    last4 = sorted(gq)[-4:]
    if len(last4) == 4 and all(q in ci and q in cs for q in last4):
        g4 = sum(gq[q] for q in last4) / 4
        c4 = sum(ci[q] + cs[q] for q in last4) / 4
        w(f"| Last 4 quarters, average | {g4:.2f} | | | {c4:.2f}pp of {g4:.2f}% = {c4 / g4:.0%} |" if g4 > 0 else f"| Last 4 quarters, average | {g4:.2f} | | | n/a |")
    w("Single-quarter shares are noisy (a weak GDP quarter inflates them); the 4-quarter average is the steadier read.")
    w("")
    p = fred.get("productivity", {}).get("obs", [])
    if len(p) >= 5:
        w(f"- Productivity (output/hour), 4-quarter change: {fmt_pct(pct(p[-1][1], p[-5][1]))} (quarter starting {p[-1][0]}); "
          f"prior quarter: {fmt_pct(pct(p[-2][1], p[-6][1]))}")
    e = fred.get("cpi_electricity", {}).get("obs", [])
    if len(e) >= 13:
        w(f"- Electricity CPI, YoY: {fmt_pct(pct(e[-1][1], e[-13][1]))} ({e[-1][0]}); 3 months earlier: {fmt_pct(pct(e[-4][1], e[-16][1])) if len(e) >= 16 else 'n/a'}")
    pc = fred.get("power_construction", {}).get("obs", [])
    if len(pc) >= 13:
        w(f"- Power construction spending, YoY: {fmt_pct(pct(pc[-1][1], pc[-13][1]))} ({pc[-1][0]}; level ${pc[-1][1] / 1000:,.1f}bn SAAR)")
    w("")

    # Market
    w("## 5. Market")
    prices = data.get("prices", {})
    if prices:
        w("Source: Yahoo Finance adjusted closes.")
        w("")
        w("| Symbol | Last | As of | 1w | 1m | 3m | 1y |")
        w("|---|---|---|---|---|---|---|")
        for s, ser in prices.items():
            w(f"| {s} | {ser[-1][1]:,.2f} | {ser[-1][0]} | {changes_line(ser, 'px')} |")
        w("")
        w("Relative performance, indexed to 100 one year ago (above 100 = beat SPY over the year):")
        for name, ser in data.get("ratios", {}).items():
            if ser:
                m1 = value_on_or_before(ser, d(ser[-1][0]) - dt.timedelta(days=30))
                w(f"- {name}: {ser[-1][1]:.1f} (one month ago {m1:.1f})" if m1 else f"- {name}: {ser[-1][1]:.1f}")
    else:
        w("Yahoo prices unavailable this run. Index levels from FRED:")
        for k in ("spx", "ndx"):
            s = fred.get(k)
            if s:
                w(f"- {s['label']}: {s['obs'][-1][1]:,.0f} ({s['obs'][-1][0]}); changes 1w|1m|3m|1y: {changes_line(s['obs'], 'px')}")
    w("")

    failed = {k: v for k, v in data["status"].items() if v != "ok"}
    w("## Data status")
    w("All sources OK." if not failed else "\n".join(f"- {k}: {v}" for k, v in failed.items()))
    return "\n".join(L) + "\n"


def main() -> int:
    data = build()
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "latest.json").write_text(json.dumps(data, separators=(",", ":")))
    (DATA_DIR / "summary.md").write_text(summary_md(data), encoding="utf-8")
    failed = [k for k, v in data["status"].items() if v != "ok"]
    print(f"fetch_data: {len(data['status']) - len(failed)} sources ok, {len(failed)} failed")
    for k in failed:
        print(f"  {k}: {data['status'][k]}")
    # Fail the run only if the core spend data is missing entirely.
    return 0 if data.get("hyperscaler_aggregate") else 1


if __name__ == "__main__":
    sys.exit(main())
