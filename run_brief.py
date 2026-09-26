"""The weekly pipeline: fetch the numbers, have Claude write the brief, render it.

    python run_brief.py              # full run for today
    python run_brief.py --no-agent   # refresh data and re-render the newest brief (no Claude call)

Authentication: this uses the Claude Agent SDK, which runs on your Claude
subscription when CLAUDE_CODE_OAUTH_TOKEN is set (make one with
`claude setup-token`). If ANTHROPIC_API_KEY is also set it would win and bill
the API pay-per-use, so this script removes it unless ALLOW_API_KEY=1.

Optional env: BRIEF_MODEL (model id), BRIEF_MAX_TURNS (default 80),
BRIEF_DATE (YYYY-MM-DD, default today).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"]


def step(msg: str) -> None:
    print(f"\n=== {msg}", flush=True)


def build_prompt(today: str, out_rel: str, prev: Path | None) -> str:
    prev_line = (
        f"The previous brief is briefs/{prev.name} (news window starts the day after its issue_date)."
        if prev
        else "There is no previous brief. Use the last 7 days as the news window."
    )
    return (
        f"Today is {today}. Write this week's AI build-out brief.\n\n"
        "Follow BRIEF.md exactly. Read, in this order: BRIEF.md, THESIS.md, data/summary.md. "
        f"{prev_line}\n\n"
        f"Write your output as JSON to {out_rel} and do not create or modify any other file. "
        "When the file is written and you have checked every number against data/summary.md or a linked source, stop."
    )


async def run_agent(prompt: str) -> None:
    from claude_agent_sdk import (  # imported here so --no-agent works without the SDK
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        query,
    )

    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        tools=AGENT_TOOLS,  # no shell: the agent reads, searches and writes one file
        allowed_tools=AGENT_TOOLS,
        permission_mode="acceptEdits",
        setting_sources=[],  # ignore any local Claude Code settings; BRIEF.md is the spec
        max_turns=int(os.environ.get("BRIEF_MAX_TURNS", "80")),
        model=os.environ.get("BRIEF_MODEL") or None,
    )
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    arg = block.input.get("query") or block.input.get("url") or block.input.get("file_path") or ""
                    print(f"  [{block.name}] {str(arg)[:110]}", flush=True)
                elif isinstance(block, TextBlock) and block.text.strip():
                    print(f"  {block.text.strip()[:200]}", flush=True)
        elif isinstance(msg, ResultMessage):
            print(f"  agent finished: {msg.subtype}, {msg.num_turns} turns, {msg.duration_ms / 1000:.0f}s", flush=True)
            if msg.is_error:
                raise RuntimeError(f"agent error: {msg.subtype} {msg.errors or ''}")


def main() -> int:
    no_agent = "--no-agent" in sys.argv
    today = os.environ.get("BRIEF_DATE") or dt.date.today().isoformat()

    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("ALLOW_API_KEY") != "1":
        print("Note: ANTHROPIC_API_KEY was set; ignoring it so this run uses your Claude subscription.")
        os.environ.pop("ANTHROPIC_API_KEY")
    if not no_agent and not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("Note: CLAUDE_CODE_OAUTH_TOKEN is not set; relying on an existing `claude` login on this machine.")

    step("1/3 Fetching data")
    if subprocess.call([sys.executable, "fetch_data.py"], cwd=ROOT) != 0:
        print("Core spend data is missing; stopping before the agent runs.")
        return 1

    briefs_dir = ROOT / "briefs"
    briefs_dir.mkdir(exist_ok=True)
    if not no_agent:
        out = briefs_dir / f"{today}.json"
        prev = next((p for p in sorted(briefs_dir.glob("*.json"), reverse=True) if p.stem < today), None)
        if out.exists():
            out.rename(out.with_suffix(".json.bak"))
        step(f"2/3 Claude writes the brief -> briefs/{out.name}")
        asyncio.run(run_agent(build_prompt(today, f"briefs/{out.name}", prev)))
        if not out.exists():
            print("The agent did not write the brief file.")
            return 1
        try:
            from render import validate

            validate(json.loads(out.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"The brief is not valid: {e}")
            return 1
    else:
        step("2/3 Skipping the agent (--no-agent)")

    step("3/3 Rendering")
    return subprocess.call([sys.executable, "render.py"], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
