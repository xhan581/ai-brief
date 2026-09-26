"""Hand-built SVG charts for the brief.

Every chart is drawn from data/latest.json by code, never by the agent, so the
pictures always match the numbers. Each SVG carries its own light/dark styles,
so it works inline in the HTML page and as a standalone image on GitHub.

Palette: the validated categorical order (blue, orange, aqua, yellow, magenta),
with separate steps for dark mode. Text never uses a series color.
"""

from __future__ import annotations

import datetime as dt
import html
import math

W = 680  # viewBox width; charts scale to their container

LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]

LIGHT_RULES = {
    ".c-bg": "fill:#fcfcfb", ".c-ink": "fill:#0b0b0b", ".c-ink2": "fill:#52514e", ".c-mute": "fill:#898781",
    ".c-grid": "stroke:#e1e0d9;stroke-width:1", ".c-axis": "stroke:#c3c2b7;stroke-width:1",
    ".c-ref": "stroke:#898781;stroke-width:1", ".c-neutral": "fill:#b5b3ab", ".c-gap": "stroke:#fcfcfb",
    **{f".s{i}": f"fill:{c}" for i, c in enumerate(LIGHT)},
    **{f".l{i}": f"stroke:{c}" for i, c in enumerate(LIGHT)},
}
DARK_RULES = {
    ".c-bg": "fill:#1a1a19", ".c-ink": "fill:#ffffff", ".c-ink2": "fill:#c3c2b7", ".c-mute": "fill:#898781",
    ".c-grid": "stroke:#2c2c2a", ".c-axis": "stroke:#383835", ".c-neutral": "fill:#5a5955", ".c-gap": "stroke:#1a1a19",
    **{f".s{i}": f"fill:{c}" for i, c in enumerate(DARK)},
    **{f".l{i}": f"stroke:{c}" for i, c in enumerate(DARK)},
}
FONT_RULES = (
    'svg text{font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:12px}'
    'svg .c-num{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:11px}'
    "svg .c-title{font-size:13px;font-weight:600}"
    "svg .c-hit{fill:transparent}svg .c-hit:hover{fill:rgba(128,128,128,.15)}"
)


def _style() -> str:
    """Same class names and colors in every chart, so repeating the block inline is harmless.
    Dark mode follows the OS setting unless the page stamps data-theme."""
    light = "".join(f"{k}{{{v}}}" for k, v in LIGHT_RULES.items())
    dark_os = "".join(f':root:not([data-theme="light"]) {k}{{{v}}}' for k, v in DARK_RULES.items())
    dark_toggle = "".join(f':root[data-theme="dark"] {k}{{{v}}}' for k, v in DARK_RULES.items())
    return light + FONT_RULES + "@media (prefers-color-scheme: dark){" + dark_os + "}" + dark_toggle


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def svg_wrap(cid: str, h: int, body: str, title: str, desc: str) -> str:
    return (
        f'<svg id="{cid}" viewBox="0 0 {W} {h}" width="100%" role="img" aria-labelledby="{cid}-t {cid}-d" '
        f'xmlns="http://www.w3.org/2000/svg" style="max-width:{W}px;height:auto;display:block">'
        f"<title id=\"{cid}-t\">{esc(title)}</title><desc id=\"{cid}-d\">{esc(desc)}</desc>"
        f"<style>{_style()}</style>"
        f'<rect class="c-bg" x="0" y="0" width="{W}" height="{h}" rx="6"/>{body}</svg>'
    )


# ---------------------------------------------------------------------------
# Scales and ticks
# ---------------------------------------------------------------------------


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi == lo:
        hi = lo + 1
    span = hi - lo
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10 * mag)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + step * 0.001:
        ticks.append(round(t, 10))
        t += step
    if ticks[-1] < hi:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


class Lin:
    def __init__(self, d0, d1, r0, r1):
        self.d0, self.d1, self.r0, self.r1 = d0, d1, r0, r1

    def __call__(self, v):
        if self.d1 == self.d0:
            return (self.r0 + self.r1) / 2
        return self.r0 + (v - self.d0) / (self.d1 - self.d0) * (self.r1 - self.r0)


def fmt_tick(v: float, unit: str) -> str:
    if unit == "bn":
        return f"${v:,.0f}bn"
    if unit == "%":
        return f"{v:,.0f}%" if abs(v) >= 10 or v == int(v) else f"{v:,.1f}%"
    if unit == "pct2":
        return f"{v:.2f}%"
    if unit == "bp":
        return f"{v:,.0f}bp"
    if unit == "pp":
        return f"{v:.1f}"
    return f"{v:,.0f}"


def y_axis(ys: Lin, ticks, x0, x1, unit) -> str:
    out = []
    for t in ticks:
        y = ys(t)
        out.append(f'<line class="c-grid" x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="c-mute c-num" x="{x0 - 8}" y="{y + 4:.1f}" text-anchor="end">{esc(fmt_tick(t, unit))}</text>')
    return "".join(out)


def legend(items: list[tuple[int | str, str]], x: int, y: int) -> str:
    """items: (slot index or 'neutral', label). Swatch carries color; text stays ink."""
    out, cx = [], x
    for slot, label in items:
        cls = "c-neutral" if slot == "neutral" else f"s{slot}"
        out.append(f'<rect class="{cls}" x="{cx}" y="{y - 9}" width="10" height="10" rx="2"/>')
        out.append(f'<text class="c-ink2" x="{cx + 15}" y="{y}">{esc(label)}</text>')
        cx += 15 + 7.2 * len(label) + 18
    return "".join(out)


def rounded_col(x, y_top, w, y_base, cls, title, r=4) -> str:
    """Column with 4px rounded data-end, square at the baseline."""
    h = y_base - y_top
    if h <= 0:
        return ""
    r = min(r, h, w / 2)
    p = (f"M{x:.1f},{y_base:.1f} L{x:.1f},{y_top + r:.1f} Q{x:.1f},{y_top:.1f} {x + r:.1f},{y_top:.1f} "
         f"L{x + w - r:.1f},{y_top:.1f} Q{x + w:.1f},{y_top:.1f} {x + w:.1f},{y_top + r:.1f} L{x + w:.1f},{y_base:.1f} Z")
    return f'<path class="{cls}" d="{p}"><title>{esc(title)}</title></path>'


# ---------------------------------------------------------------------------
# Chart 1: Spend — stacked quarterly capex by company
# ---------------------------------------------------------------------------

HS = ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]


def chart_spend(data: dict) -> str:
    agg = data["hyperscaler_aggregate"]
    qs = list(agg)[-10:]
    h, top, bottom, left, right = 330, 48, 290, 62, W - 16
    ymax = max(agg[q]["capex"] for q in qs) / 1e9
    ticks = nice_ticks(0, ymax * 1.06)
    ys = Lin(0, ticks[-1], bottom, top)
    band = (right - left) / len(qs)
    bw = min(24 * 1.6, band * 0.62)
    body = [y_axis(ys, ticks, left, right, "bn")]
    for i, q in enumerate(qs):
        x = left + band * i + (band - bw) / 2
        base = 0.0
        for s, t in enumerate(HS):
            v = agg[q]["by_company"][t] / 1e9
            y0, y1 = ys(base), ys(base + v)
            is_top = s == len(HS) - 1
            label = f"{t} {q}: ${v:,.1f}bn"
            if is_top:
                body.append(rounded_col(x, y1, bw, y0, f"s{s}", label))
            else:
                body.append(f'<rect class="s{s}" x="{x:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(y0 - y1, 0):.1f}"><title>{esc(label)}</title></rect>')
            # 2px surface gap between stacked segments
            if s > 0:
                body.append(f'<line class="c-gap" x1="{x:.1f}" x2="{x + bw:.1f}" y1="{y0:.1f}" y2="{y0:.1f}" stroke-width="2"/>')
            base += v
        body.append(f'<text class="c-ink c-num" x="{x + bw / 2:.1f}" y="{ys(base) - 6:.1f}" text-anchor="middle">{base:,.0f}</text>')
        body.append(f'<text class="c-mute c-num" x="{x + bw / 2:.1f}" y="{bottom + 16}" text-anchor="middle">{q[2:]}</text>')
    body.append(f'<line class="c-axis" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/>')
    body.append(legend([(i, t) for i, t in enumerate(HS)], left, 24))
    last = qs[-1]
    desc = f"Stacked columns of quarterly capex for {', '.join(HS)}, {qs[0]} to {last}. Latest total ${agg[last]['capex'] / 1e9:,.1f}bn."
    return svg_wrap("ch-spend", h, "".join(body), "Hyperscaler capex per quarter, $bn", desc)


# ---------------------------------------------------------------------------
# Chart 2: Funding — T4Q capex/OCF and combined long-term debt (two panels)
# ---------------------------------------------------------------------------


def chart_funding(data: dict) -> str:
    agg = data["hyperscaler_aggregate"]
    qs = [q for q in agg if agg[q].get("capex_to_ocf_t4q") is not None][-10:]
    h = 300
    body = []
    # Panel A: ratio line
    ax0, ax1, top, bottom = 56, W / 2 - 24, 56, 262
    vals = [agg[q]["capex_to_ocf_t4q"] * 100 for q in qs]
    ticks = nice_ticks(0, max(max(vals) * 1.1, 115))
    ys = Lin(0, ticks[-1], bottom, top)
    xs = Lin(0, len(qs) - 1, ax0 + 10, ax1 - 10)
    body.append('<text class="c-ink c-title" x="16" y="24">Capex as % of operating cash flow</text>')
    body.append('<text class="c-ink2" x="16" y="42">Trailing 4 quarters, five hyperscalers combined</text>')
    body.append(y_axis(ys, ticks, ax0, ax1, "%"))
    y100 = ys(100)
    body.append(f'<line class="c-ref" x1="{ax0}" x2="{ax1}" y1="{y100:.1f}" y2="{y100:.1f}" stroke-dasharray="0"/>')
    body.append(f'<text class="c-ink2" x="{ax1}" y="{y100 - 6:.1f}" text-anchor="end">100% = all operating cash</text>')
    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(vals))
    body.append(f'<polyline class="l0" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>')
    for i, (q, v) in enumerate(zip(qs, vals)):
        body.append(f'<circle class="c-hit" cx="{xs(i):.1f}" cy="{ys(v):.1f}" r="9"><title>{q}: {v:.0f}%</title></circle>')
    lx, ly = xs(len(qs) - 1), ys(vals[-1])
    body.append(f'<circle class="s0 c-gap" cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" stroke-width="2"/>')
    body.append(f'<text class="c-ink c-num" x="{lx - 8:.1f}" y="{ly - 10:.1f}" text-anchor="end">{vals[-1]:.0f}%</text>')
    for i in (0, len(qs) - 1):
        body.append(f'<text class="c-mute c-num" x="{xs(i):.1f}" y="{bottom + 16}" text-anchor="middle">{qs[i][2:]}</text>')
    body.append(f'<line class="c-axis" x1="{ax0}" x2="{ax1}" y1="{bottom}" y2="{bottom}"/>')

    # Panel B: combined long-term debt (non-current), columns
    bx0, bx1 = W / 2 + 44, W - 16
    # Same quarters and numbers as the aggregate table in data/summary.md; gaps stay visible.
    debt = [(q, (agg[q].get("debt_lt") or 0) / 1e9 or None) for q in list(agg)[-8:]]

    body.append(f'<text class="c-ink c-title" x="{W / 2 + 8}" y="24">Long-term debt, combined</text>')
    body.append(f'<text class="c-ink2" x="{W / 2 + 8}" y="42">Non-current, balance sheet, $bn</text>')
    present = [i for i, (_, v) in enumerate(debt) if v]
    if present:
        dt_ticks = nice_ticks(0, max(v for _, v in debt if v) * 1.12)
        dys = Lin(0, dt_ticks[-1], bottom, top)
        body.append(y_axis(dys, dt_ticks, bx0, bx1, "bn"))
        band = (bx1 - bx0) / len(debt)
        bw = min(24, band * 0.6)
        ends = (present[0], present[-1])
        for i, (q, v) in enumerate(debt):
            x = bx0 + band * i + (band - bw) / 2
            if v:
                body.append(rounded_col(x, dys(v), bw, bottom, "s0", f"{q}: ${v:,.1f}bn"))
                if i in ends:
                    body.append(f'<text class="c-ink c-num" x="{x + bw / 2:.1f}" y="{dys(v) - 6:.1f}" text-anchor="middle">{v:,.1f}</text>')
            else:
                body.append(f'<text class="c-mute c-num" x="{x + bw / 2:.1f}" y="{bottom - 6}" text-anchor="middle">n/a</text>')
            if i in (0, len(debt) - 1):
                body.append(f'<text class="c-mute c-num" x="{x + bw / 2:.1f}" y="{bottom + 16}" text-anchor="middle">{q[2:]}</text>')
        body.append(f'<line class="c-axis" x1="{bx0}" x2="{bx1}" y1="{bottom}" y2="{bottom}"/>')
    desc = f"Left: trailing-4-quarter capex as a share of operating cash flow, {qs[0]} {vals[0]:.0f}% to {qs[-1]} {vals[-1]:.0f}%. Right: combined non-current long-term debt."
    return svg_wrap("ch-funding", h, "".join(body), "How the build-out is funded", desc)


# ---------------------------------------------------------------------------
# Line-chart helper for daily series
# ---------------------------------------------------------------------------


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def line_panel(series: list[tuple[int, str, list[list]]], x0, x1, top, bottom, unit, scale=1.0, zero=False, ref=None):
    """series: (slot, label, [[date, value], ...]). Shared x axis by date."""
    out = []
    all_d = [_d(p[0]) for _, _, s in series for p in s]
    d0, d1 = min(all_d), max(all_d)
    vals = [p[1] * scale for _, _, s in series for p in s]
    lo, hi = min(vals), max(vals)
    if zero:
        lo = min(lo, 0)
    pad = (hi - lo) * 0.08 or 1
    floor = lo if zero else (lo - pad if lo - pad < 0 <= lo and False else lo - pad)
    if lo >= 0 and floor < 0:
        floor = 0
    ticks = nice_ticks(floor, hi + pad, 4)
    ys = Lin(ticks[0], ticks[-1], bottom, top)
    xs = Lin(0, (d1 - d0).days, x0, x1)
    out.append(y_axis(ys, ticks, x0, x1, unit))
    if ref is not None and ticks[0] <= ref <= ticks[-1]:
        out.append(f'<line class="c-ref" x1="{x0}" x2="{x1}" y1="{ys(ref):.1f}" y2="{ys(ref):.1f}"/>')
    ends = []
    for slot, label, s in series:
        pts = " ".join(f"{xs((_d(a) - d0).days):.1f},{ys(b * scale):.1f}" for a, b in s)
        out.append(f'<polyline class="l{slot}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>')
        step = max(1, len(s) // 40)
        for a, b in s[::step] + [s[-1]]:
            v = b * scale
            out.append(f'<circle class="c-hit" cx="{xs((_d(a) - d0).days):.1f}" cy="{ys(v):.1f}" r="6"><title>{esc(label)} {a}: {esc(fmt_val(v, unit))}</title></circle>')
        ex, ey = xs((_d(s[-1][0]) - d0).days), ys(s[-1][1] * scale)
        out.append(f'<circle class="s{slot} c-gap" cx="{ex:.1f}" cy="{ey:.1f}" r="4" stroke-width="2"/>')
        ends.append([ey, fmt_val(s[-1][1] * scale, unit), ex])
    # end labels, nudged apart minimally; the legend remains the identity channel
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 13:
            ends[i][0] = ends[i - 1][0] + 13
    for ey, txt, ex in ends:
        out.append(f'<text class="c-ink c-num" x="{ex + 7:.1f}" y="{ey + 4:.1f}">{esc(txt)}</text>')
    # x labels: first and last date, plus year starts
    out.append(f'<line class="c-axis" x1="{x0}" x2="{x1}" y1="{bottom}" y2="{bottom}"/>')
    out.append(f'<text class="c-mute c-num" x="{x0}" y="{bottom + 16}" text-anchor="start">{d0.strftime("%b %Y")}</text>')
    out.append(f'<text class="c-mute c-num" x="{x1}" y="{bottom + 16}" text-anchor="end">{d1.strftime("%b %d, %Y")}</text>')
    return "".join(out)


def fmt_val(v: float, unit: str) -> str:
    if unit == "bp":
        return f"{v:,.0f}bp"
    if unit == "pct2":
        return f"{v:.2f}%"
    if unit == "%":
        return f"{v:.1f}%"
    return f"{v:,.1f}"


def trim(series: list[list], days: int) -> list[list]:
    last = _d(series[-1][0])
    return [p for p in series if _d(p[0]) >= last - dt.timedelta(days=days)]


# ---------------------------------------------------------------------------
# Chart 3: Credit and rates
# ---------------------------------------------------------------------------


def chart_credit(data: dict) -> str:
    f = data["fred"]
    h = 300
    body = []
    body.append('<text class="c-ink c-title" x="16" y="24">IG and BBB spreads</text>')
    body.append(legend([(0, "IG OAS"), (1, "BBB OAS")], 16, 44))
    ser = [(0, "IG OAS", trim(f["ig_oas"]["obs"], 3 * 365)), (1, "BBB OAS", trim(f["bbb_oas"]["obs"], 3 * 365))]
    body.append(line_panel(ser, 56, W / 2 - 44, 62, 262, "bp", scale=100))
    body.append(f'<text class="c-ink c-title" x="{W / 2 + 8}" y="24">10y yield and term premium</text>')
    body.append(legend([(0, "10y UST"), (1, "Term premium")], W / 2 + 8, 44))
    ser2 = [(0, "10y UST", trim(f["ust10"]["obs"], 3 * 365)), (1, "Term premium", trim(f["tp10"]["obs"], 3 * 365))]
    body.append(line_panel(ser2, W / 2 + 44, W - 52, 62, 262, "pct2"))
    ig = f["ig_oas"]["obs"][-1]
    t10 = f["ust10"]["obs"][-1]
    desc = f"Left: IG and BBB option-adjusted spreads over three years; IG {ig[1] * 100:.0f}bp on {ig[0]}. Right: 10y Treasury {t10[1]:.2f}% and Kim-Wright term premium."
    return svg_wrap("ch-credit", h, "".join(body), "Cost of funding", desc)


# ---------------------------------------------------------------------------
# Chart 4: Receivers — small multiples of quarterly revenue
# ---------------------------------------------------------------------------

SUP = ["NVDA", "AVGO", "AMD", "MU", "VRT"]


def chart_receivers(data: dict) -> str:
    comps = data["companies"]
    h = 250
    body = []
    n = len(SUP)
    gap = 14
    pw = (W - 32 - gap * (n - 1)) / n
    top, bottom = 70, 212
    for i, t in enumerate(SUP):
        c = comps.get(t)
        x0 = 16 + i * (pw + gap)
        body.append(f'<text class="c-ink c-title" x="{x0}" y="24">{t}</text>')
        if not c:
            body.append(f'<text class="c-mute" x="{x0}" y="60">no data</text>')
            continue
        qs = [q for q in c["quarters"] if c["quarters"][q].get("revenue") is not None][-8:]
        vals = [c["quarters"][q]["revenue"] / 1e9 for q in qs]
        last_q = qs[-1]
        prev = c["quarters"].get(_shift(last_q, -4), {}).get("revenue")
        yoy = (c["quarters"][last_q]["revenue"] / prev - 1) * 100 if prev else None
        body.append(f'<text class="c-ink2 c-num" x="{x0}" y="42">${vals[-1]:,.1f}bn in {last_q}</text>')
        body.append(f'<text class="c-ink2 c-num" x="{x0}" y="58">{"n/a" if yoy is None else f"{yoy:+.0f}% YoY"}</text>')
        ys = Lin(0, max(vals) * 1.05, bottom, top)
        band = pw / len(qs)
        bw = min(14, band * 0.62)
        for j, (q, v) in enumerate(zip(qs, vals)):
            x = x0 + band * j + (band - bw) / 2
            body.append(rounded_col(x, ys(v), bw, bottom, "s0", f"{t} {q}: ${v:,.2f}bn", r=3))
        body.append(f'<line class="c-axis" x1="{x0}" x2="{x0 + pw}" y1="{bottom}" y2="{bottom}"/>')
        body.append(f'<text class="c-mute c-num" x="{x0}" y="{bottom + 16}">{qs[0][2:]}</text>')
        body.append(f'<text class="c-mute c-num" x="{x0 + pw}" y="{bottom + 16}" text-anchor="end">{qs[-1][2:]}</text>')
    body.append(f'<text class="c-mute" x="16" y="{h - 6}">Each panel has its own scale: compare shapes, not heights.</text>')
    return svg_wrap("ch-receivers", h, "".join(body), "Supplier revenue per quarter", "Small multiples of quarterly revenue for " + ", ".join(SUP) + ", last eight calendar quarters, each on its own scale.")


def _shift(q: str, n: int) -> str:
    y, k = int(q[:4]), int(q[-1])
    idx = y * 4 + (k - 1) + n
    return f"{idx // 4}Q{idx % 4 + 1}"


# ---------------------------------------------------------------------------
# Chart 5: Macro — GDP growth vs IT investment contribution
# ---------------------------------------------------------------------------


def chart_macro(data: dict) -> str:
    f = data["fred"]
    g = {a: b for a, b in f["gdp_growth"]["obs"]}
    ci = {a: b for a, b in f["contrib_ipe"]["obs"]}
    cs = {a: b for a, b in f["contrib_software"]["obs"]}
    qs = [q for q in sorted(g) if q in ci and q in cs][-10:]
    h, top, bottom, left, right = 300, 56, 262, 52, W - 16
    vals = [g[q] for q in qs] + [ci[q] + cs[q] for q in qs]
    ticks = nice_ticks(min(0, min(vals)), max(vals) * 1.1, 5)
    ys = Lin(ticks[0], ticks[-1], bottom, top)
    body = [y_axis(ys, ticks, left, right, "pp")]
    body.append(legend([("neutral", "Real GDP growth, % SAAR"), (0, "IT equipment + software contribution, pp")], left, 30))
    band = (right - left) / len(qs)
    bw = min(20, band * 0.3)
    y0 = ys(0)
    for i, q in enumerate(qs):
        cx = left + band * i + band / 2
        for k, (v, cls, name) in enumerate(((g[q], "c-neutral", "GDP growth"), (ci[q] + cs[q], "s0", "IT contribution"))):
            x = cx - bw - 1 + k * (bw + 2)
            tip = f"{q[:7]} {name}: {v:+.2f}"
            if v >= 0:
                body.append(rounded_col(x, ys(v), bw, y0, cls, tip))
            else:
                body.append(f'<rect class="{cls}" x="{x:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{ys(v) - y0:.1f}"><title>{esc(tip)}</title></rect>')
        d = _d(q)
        body.append(f'<text class="c-mute c-num" x="{cx:.1f}" y="{bottom + 16}" text-anchor="middle">{d.year % 100:02d}Q{(d.month - 1) // 3 + 1}</text>')
    body.append(f'<line class="c-axis" x1="{left}" x2="{right}" y1="{y0:.1f}" y2="{y0:.1f}"/>')
    last = qs[-1]
    desc = f"Grouped columns per quarter: real GDP growth versus the contribution of information-processing equipment plus software. Latest ({last}): GDP {g[last]:.1f}%, IT {ci[last] + cs[last]:.2f}pp."
    return svg_wrap("ch-macro", h, "".join(body), "How much of GDP growth is IT investment", desc)


# ---------------------------------------------------------------------------
# Chart 6: Market — relative performance vs SPY
# ---------------------------------------------------------------------------

RATIO_ORDER = ["SMH/SPY", "Hyperscalers/SPY", "RSP/SPY", "XLU/SPY"]
RATIO_LABEL = {
    "SMH/SPY": "Semis (SMH)",
    "Hyperscalers/SPY": "Hyperscalers (equal wt)",
    "RSP/SPY": "Equal-weight S&P (RSP)",
    "XLU/SPY": "Utilities (XLU)",
}


def chart_market(data: dict) -> str | None:
    r = data.get("ratios") or {}
    names = [n for n in RATIO_ORDER if r.get(n)]
    if not names:
        return None
    h = 320
    body = [legend([(i, RATIO_LABEL[n]) for i, n in enumerate(names)], 16, 26)]
    body.append('<text class="c-ink2" x="16" y="46">Each line is price relative to SPY, indexed to 100 a year ago. Above 100 = beat the market.</text>')
    ser = [(i, RATIO_LABEL[n], r[n]) for i, n in enumerate(names)]
    body.append(line_panel(ser, 52, W - 64, 70, 286, "idx", ref=100))
    desc = "Relative performance versus SPY over one year: " + "; ".join(f"{RATIO_LABEL[n]} {r[n][-1][1]:.0f}" for n in names) + "."
    return svg_wrap("ch-market", h, "".join(body), "Who the market is paying", desc)


def all_charts(data: dict) -> dict[str, str]:
    out = {}
    for key, fn in (("spend", chart_spend), ("funding", chart_funding), ("credit", chart_credit),
                    ("receivers", chart_receivers), ("macro", chart_macro), ("market", chart_market)):
        try:
            svg = fn(data)
            if svg:
                out[key] = svg
        except Exception as e:  # noqa: BLE001 - a broken chart must not kill the brief
            out[key] = f'<p class="chart-missing">Chart unavailable this week ({esc(e)}).</p>'
    return out
