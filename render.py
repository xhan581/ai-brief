"""Turn this week's brief (briefs/<date>.json) plus the data into readable pages.

Outputs:
  site/<date>/index.html      self-contained page (charts inline)
  site/<date>/charts/*.svg    the same charts as standalone images
  site/index.html             copy of the newest issue
  LATEST.md                   the newest issue as markdown (renders on GitHub, phone-friendly)

Usage: python render.py [briefs/YYYY-MM-DD.json]   (default: newest brief)
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

from charts import all_charts

ROOT = Path(__file__).resolve().parent
SECTIONS = [
    ("spend", "Spend", "Is hyperscaler capex still accelerating?", ["spend"]),
    ("funding", "Funding", "Who is paying for it, and at what price?", ["funding", "credit"]),
    ("receivers", "Receivers", "Is the money showing up as supplier revenue?", ["receivers"]),
    ("macro", "Macro", "Is it showing up in the economy?", ["macro"]),
    ("market", "Market", "How is the market pricing it?", ["market"]),
]
STATUS = {
    "clear": ("Clear", "○"),
    "near": ("Near", "◐"),
    "hit": ("Hit", "●"),
}


class BriefError(ValueError):
    pass


def validate(b: dict) -> None:
    need = ["issue_date", "headline", "verdict", "what_changed", "sections", "tripwires", "sources"]
    missing = [k for k in need if k not in b]
    if missing:
        raise BriefError(f"brief is missing keys: {missing}")
    for key, *_ in SECTIONS:
        s = b["sections"].get(key)
        if not s or not s.get("claim") or "body" not in s:
            raise BriefError(f"section '{key}' is missing or has no claim/body")
    for t in b["tripwires"]:
        if t.get("status") not in STATUS:
            raise BriefError(f"tripwire {t.get('id')} has bad status {t.get('status')!r}")


def e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def safe_url(u: str) -> str:
    return u if isinstance(u, str) and re.match(r"^https?://", u) else "#"


CSS = """
:root{
  --bg:#f5f6f4;--surface:#fcfcfb;--ink:#111413;--ink2:#4c5350;--mute:#7d827f;--rule:#dcdfdb;
  --accent:#1d5fbf;--good:#0ca30c;--warn:#b27a00;--crit:#d03b3b;--chip:#eceee9;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  color-scheme:dark;--bg:#0f100f;--surface:#1a1a19;--ink:#f1f2ef;--ink2:#c3c2b7;--mute:#8d918c;--rule:#2d2f2c;
  --accent:#7fb0f0;--good:#35c235;--warn:#fab219;--crit:#e66767;--chip:#232522;}}
:root[data-theme="dark"]{
  color-scheme:dark;--bg:#0f100f;--surface:#1a1a19;--ink:#f1f2ef;--ink2:#c3c2b7;--mute:#8d918c;--rule:#2d2f2c;
  --accent:#7fb0f0;--good:#35c235;--warn:#fab219;--crit:#e66767;--chip:#232522;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding-inline:20px;padding-block:28px 64px;display:flex;flex-direction:column;gap:36px}
a{color:var(--accent);text-underline-offset:2px}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.mono{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.eyebrow{font:500 12px/1.4 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--mute)}
header{display:flex;flex-direction:column;gap:10px}
h1{font-size:clamp(24px,4.2vw,32px);line-height:1.2;font-weight:600;margin:0;text-wrap:balance;letter-spacing:-.01em}
.verdict{font-size:17px;line-height:1.6;margin:0;max-width:65ch}
h2{font-size:13px;font-weight:600;margin:0;color:var(--ink2);letter-spacing:.04em;text-transform:uppercase}
.changed ul{margin:10px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:6px;max-width:65ch}
.chain{display:flex;flex-direction:column;gap:40px}
.step{display:grid;grid-template-columns:44px 1fr;gap:0 14px;border-top:1px solid var(--rule);padding-top:20px}
.step-n{font:600 28px/1 "IBM Plex Mono",ui-monospace,monospace;color:var(--mute)}
.step-body{display:flex;flex-direction:column;gap:12px;min-width:0}
.q{margin:0;color:var(--mute);font-size:13px}
.claim{margin:0;font-size:19px;line-height:1.4;font-weight:600;text-wrap:balance}
.body{margin:0;max-width:65ch;color:var(--ink)}
.pill{display:inline-block;font:500 11px/1 "IBM Plex Mono",ui-monospace,monospace;padding:4px 7px;border-radius:4px;background:var(--chip);color:var(--ink2);vertical-align:middle;margin-left:8px;letter-spacing:.03em}
.pill.new{color:var(--ink);box-shadow:inset 0 0 0 1px var(--accent)}
figure{margin:4px 0 0;background:var(--surface);border-radius:8px;padding:6px;overflow-x:auto}
.evidence{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink2)}
.evidence li::before{content:"↗ ";color:var(--mute)}
table{border-collapse:collapse;width:100%;font-size:14px}
.tw-wrap{overflow-x:auto}
th{text-align:left;font-weight:500;color:var(--mute);font-size:12px;padding:6px 10px 6px 0;border-bottom:1px solid var(--rule)}
td{padding:9px 10px 9px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.st{white-space:nowrap;font-weight:600}
.st .ic{display:inline-block;width:1.1em}
.st-clear{color:var(--good)}.st-near{color:var(--warn)}.st-hit{color:var(--crit)}
.sugg{margin:10px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:6px;max-width:65ch}
.sources{columns:2 280px;column-gap:28px;margin:10px 0 0;padding-left:18px;font-size:13px}
.sources li{break-inside:avoid;margin-bottom:6px}
footer{border-top:1px solid var(--rule);padding-top:14px;font-size:12px;color:var(--mute);display:flex;flex-direction:column;gap:4px}
.chart-missing{color:var(--mute);font-size:13px;margin:8px}
@media (max-width:520px){.step{grid-template-columns:1fr}.step-n{font-size:20px;margin-bottom:6px}}
"""


def render_html(b: dict, data: dict, charts: dict[str, str]) -> str:
    out = []
    w = out.append
    w("<title>AI Build-out Brief</title>")
    w('<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">')
    w('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')
    w(f"<style>{CSS}</style>")
    w('<div class="wrap">')
    window = f"{e(b.get('window_start', ''))} → {e(b['issue_date'])}" if b.get("window_start") else e(b["issue_date"])
    w(f'<header><div class="eyebrow">AI build-out brief · {e(b["issue_date"])} · news window {window}</div>')
    w(f'<h1>{e(b["headline"])}</h1><p class="verdict">{e(b["verdict"])}</p></header>')

    if b.get("what_changed"):
        w('<section class="changed"><h2>What changed this week</h2><ul>')
        for item in b["what_changed"]:
            w(f"<li>{e(item)}</li>")
        w("</ul></section>")

    w('<section class="chain">')
    for n, (key, label, question, chart_keys) in enumerate(SECTIONS, 1):
        s = b["sections"][key]
        pill = '<span class="pill new">New this week</span>' if s.get("changed") else '<span class="pill">No change</span>'
        w(f'<article class="step" id="{key}"><div class="step-n">{n}</div><div class="step-body">')
        w(f"<h2>{label}{pill}</h2><p class=\"q\">{e(question)}</p>")
        w(f'<p class="claim">{e(s["claim"])}</p><p class="body">{e(s["body"])}</p>')
        for ck in chart_keys:
            if ck in charts:
                w(f"<figure>{charts[ck]}</figure>")
        ev = [x for x in s.get("evidence", []) if x.get("url")]
        if ev:
            w('<ul class="evidence">')
            for x in ev:
                w(f'<li><a href="{e(safe_url(x["url"]))}" target="_blank" rel="noopener">{e(x.get("text") or x["url"])}</a></li>')
            w("</ul>")
        w("</div></article>")
    w("</section>")

    w('<section><h2>Tripwires</h2><div class="tw-wrap"><table><thead><tr><th>ID</th><th>Tripwire</th><th>Status</th><th>Reading</th></tr></thead><tbody>')
    for t in b["tripwires"]:
        label, icon = STATUS[t["status"]]
        w(f'<tr><td class="mono">{e(t.get("id"))}</td><td>{e(t.get("name"))}</td>'
          f'<td class="st st-{t["status"]}"><span class="ic" aria-hidden="true">{icon}</span>{label}</td><td>{e(t.get("reading"))}</td></tr>')
    w("</tbody></table></div></section>")

    if b.get("thesis_suggestions"):
        w('<section><h2>Suggested edits to your thesis</h2><ul class="sugg">')
        for s in b["thesis_suggestions"]:
            w(f"<li>{e(s)}</li>")
        w("</ul></section>")

    if b.get("sources"):
        w('<section><h2>Sources</h2><ol class="sources">')
        for s in b["sources"]:
            w(f'<li><a href="{e(safe_url(s.get("url")))}" target="_blank" rel="noopener">{e(s.get("title") or s.get("url"))}</a></li>')
        w("</ol></section>")

    failed = [k for k, v in data.get("status", {}).items() if v != "ok"]
    w("<footer>")
    w(f"<div>Numbers and charts: generated by code from SEC XBRL filings, FRED and Yahoo Finance at {e(data.get('generated_at'))}. "
      "Full tables in data/summary.md. Text: Claude, following BRIEF.md.</div>")
    w(f"<div>Data sources failed this run: {e(', '.join(failed))}</div>" if failed else "<div>All data sources responded this run.</div>")
    w("</footer></div>")
    return "\n".join(out)


def render_md(b: dict, chart_dir_rel: str, charts: dict[str, str]) -> str:
    L = [f"# {b['headline']}", "", f"*AI build-out brief · {b['issue_date']}*", "", b["verdict"], ""]
    if b.get("what_changed"):
        L += ["**What changed this week**", ""] + [f"- {x}" for x in b["what_changed"]] + [""]
    for n, (key, label, question, chart_keys) in enumerate(SECTIONS, 1):
        s = b["sections"][key]
        tag = "new this week" if s.get("changed") else "no change"
        L += [f"## {n}. {label} ({tag})", "", f"**{s['claim']}**", "", s["body"], ""]
        for ck in chart_keys:
            if ck in charts and charts[ck].startswith("<svg"):
                L += [f"![{ck}]({chart_dir_rel}/{ck}.svg)", ""]
        for x in s.get("evidence", []):
            if x.get("url"):
                L.append(f"- [{x.get('text') or x['url']}]({x['url']})")
        L.append("")
    L += ["## Tripwires", "", "| ID | Tripwire | Status | Reading |", "|---|---|---|---|"]
    for t in b["tripwires"]:
        label, icon = STATUS[t["status"]]
        L.append(f"| {t.get('id')} | {t.get('name')} | {icon} {label} | {t.get('reading')} |")
    if b.get("thesis_suggestions"):
        L += ["", "## Suggested edits to your thesis", ""] + [f"- {x}" for x in b["thesis_suggestions"]]
    if b.get("sources"):
        L += ["", "## Sources", ""] + [f"{i}. [{s.get('title') or s.get('url')}]({s.get('url')})" for i, s in enumerate(b["sources"], 1)]
    return "\n".join(L) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        briefs = sorted((ROOT / "briefs").glob("*.json"))
        if not briefs:
            print("render: no briefs found")
            return 1
        path = briefs[-1]
    b = json.loads(path.read_text(encoding="utf-8"))
    validate(b)
    data = json.loads((ROOT / "data" / "latest.json").read_text())
    charts = all_charts(data)

    out_dir = ROOT / "site" / b["issue_date"]
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)
    for k, svg in charts.items():
        if svg.startswith("<svg"):
            (out_dir / "charts" / f"{k}.svg").write_text(svg, encoding="utf-8")
    page = render_html(b, data, charts)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    shutil.copyfile(out_dir / "index.html", ROOT / "site" / "index.html")
    (ROOT / "LATEST.md").write_text(render_md(b, f"site/{b['issue_date']}/charts", charts), encoding="utf-8")
    print(f"render: wrote {out_dir / 'index.html'} and LATEST.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
