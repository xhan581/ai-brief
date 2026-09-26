# AI build-out brief

A one-page weekly read on the AI infrastructure build-out: is it still on
track, who is paying for it, and did anything this week move the picture
toward or away from your thesis.

**Latest issue: [LATEST.md](LATEST.md)** (renders on GitHub, including on your phone).

## How it works

Every Monday morning a GitHub Action runs three steps:

1. **Code pulls the numbers** (`fetch_data.py`): hyperscaler capex, cash
   flow, leases and debt from SEC filings; supplier revenue; IG/BBB/HY
   spreads, Treasuries and term premium, GDP contributions, electricity
   prices and productivity from FRED; ETF and stock prices from Yahoo. Output:
   `data/summary.md` (tables) and `data/latest.json`.
2. **Claude does the reading and writes the brief** (`run_brief.py`, via the
   Claude Agent SDK on your subscription). It follows `BRIEF.md`, judges the
   week against `THESIS.md`, searches the web for the week's news, and writes
   `briefs/<date>.json`. It can only read files, search the web and write that
   one file.
3. **Code draws the charts and pages** (`render.py`, `charts.py`): 
   `site/<date>/index.html`, `site/index.html` and `LATEST.md`.

Numbers come from code; words come from Claude. Every number in the text must
match `data/summary.md` or a linked source.

## The two files you edit

- **`THESIS.md`**: your view and your tripwires. The first version is a draft
  I wrote from the 2026-09-25 data. Rewrite it so it's yours. The brief never
  changes it; it only suggests edits.
- **`BRIEF.md`**: the instructions Claude follows every week (sections,
  sources to check, rules, output format). When a section isn't useful, change
  it here.

## One-time setup

1. **Put this folder on GitHub.** First move the workflow file into place
   (remote tools can't write into `.github` folders, so it ships in `setup/`).
   In PowerShell, from this folder:
   ```
   mkdir .github\workflows
   move setup\weekly-brief.yml .github\workflows\
   ```
   Then create a new *private* repository (e.g. `ai-brief`) on github.com
   with no README, and push:
   ```
   git init -b main
   git add .
   git commit -m "AI build-out brief"
   git remote add origin https://github.com/<you>/ai-brief.git
   git push -u origin main
   ```
2. **Get a subscription token.** On your laptop, install Claude Code
   (`npm install -g @anthropic-ai/claude-code`), then run
   `claude setup-token`. Approve in the browser and copy the token it prints
   (valid for one year).
3. **Give it to GitHub.** In the repository: Settings → Secrets and
   variables → Actions.
   - *Secrets* tab → New secret: name `CLAUDE_CODE_OAUTH_TOKEN`, value = the token.
   - *Variables* tab → New variable: name `SEC_USER_AGENT`, value = your name
     and an email address, e.g. `Jane Doe jane@example.com`. (The SEC asks
     automated users to identify themselves.)
   - Do **not** add an `ANTHROPIC_API_KEY` secret. It would bill the API
     instead of your subscription. The runner removes one if it finds it.
4. **Test it.** Actions tab → "Weekly AI build-out brief" → Run workflow.
   It takes roughly 5 to 15 minutes. When it finishes, open `LATEST.md`.

After that it runs every Monday at about 6:17am New York time.

## Running it yourself

```
pip install -r requirements.txt
python run_brief.py              # full run (uses your `claude` login or CLAUDE_CODE_OAUTH_TOKEN)
python run_brief.py --no-agent   # refresh numbers and re-render the latest brief, no Claude call
```

## Limits to know about

- **Usage** counts against your Claude subscription's limits, the same pool
  as your chats. Anthropic has changed how SDK usage is billed before; see
  https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
- **Name-level credit** (Oracle CDS, where specific bonds trade, new-issue
  concessions) isn't in any free data feed. It comes from Claude's news
  reading, so it's only as good as what's published.
- **Yahoo Finance** sometimes blocks cloud servers. If it does, the market
  section falls back to S&P 500 and Nasdaq-100 levels from FRED and the brief
  says so.
- **Fiscal quarters** are mapped to calendar quarters by their midpoint
  (Oracle's June–August quarter is Q3), so all five spenders line up.
