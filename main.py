#!/usr/bin/env python3
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from openai import AsyncOpenAI

# --- Rich TUI ---
from rich.live import Live
from rich.table import Table
from rich.console import Console, Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

console = Console()

# ------------------ Config ------------------

AGENT_MODELS: List[str] = [
    "gpt-5",        # Planner
    "gpt-5-mini",   # Explainer
    "gpt-5-nano",   # Optimizer
    "gpt-5",        # Skeptic
]

AGENT_ROLES: List[str] = [
    "You are the Planner. Produce a tight, step-by-step plan tailored to the user prompt.",
    "You are the Explainer. Give a clear, concise explanation anyone can follow.",
    "You are the Optimizer. Improve efficiency, latency, and cost; propose a refined approach.",
    "You are the Skeptic. Find flaws, edge cases, and risks; propose mitigations.",
]

SYNTH_MODEL = "gpt-5"
AGENT_MAX_TOKENS = 500
SYNTH_MAX_TOKENS = 900

# GPT-5 per docs: minimal reasoning + verbosity control (no temperature for reasoning models)
AGENT_REASONING = {"effort": "minimal"}   # fastest agents
SYNTH_REASONING = {"effort": "medium"}    # judge thinks a bit more
AGENT_TEXT = {"verbosity": "low"}
SYNTH_TEXT = {"verbosity": "low"}

# Settings (toggle via /settings)
LOG_ALL_TO_FILE: bool = False   # when True, dump full trace to ./gpt5_trace_<ts>.txt


# ------------------ State ------------------

@dataclass
class AgentState:
    name: str
    model: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    ok: Optional[bool] = None          # None=running, True=done, False=error
    error: Optional[str] = None
    output_text: Optional[str] = None

    @property
    def elapsed(self) -> float:
        end = self.ended_at if self.ended_at else time.time()
        return max(0.0, end - self.started_at)


# ------------------ OpenAI Calls ------------------

def _extract_output_text(resp) -> str:
    # Prefer convenience property if present
    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
    # Fallback: scan structured output
    try:
        chunks = []
        for item in getattr(resp, "output", []):
            for block in getattr(item, "content", []):
                if getattr(block, "type", None) == "output_text":
                    chunks.append(getattr(block, "text", ""))
        if chunks:
            return "".join(chunks).strip()
    except Exception:
        pass
    return str(resp)


async def call_agent(client: AsyncOpenAI, role: str, model: str, user_prompt: str) -> str:
    resp = await client.responses.create(
        model=model,
        instructions=role,
        input=user_prompt,                 # single-string input per GPT-5 Responses API
        reasoning=AGENT_REASONING,         # {"effort":"minimal"}
        text=AGENT_TEXT,                   # {"verbosity":"low"}
        max_output_tokens=AGENT_MAX_TOKENS,
    )
    return _extract_output_text(resp)


async def call_synth(client: AsyncOpenAI, model: str, user_prompt: str,
                     panel: Dict[str, Tuple[str, str]]) -> str:
    stitched = "\n\n".join(
        f"### {name} ({mdl})\n{text.strip()}" for name, (mdl, text) in panel.items()
    )
    synth_instructions = (
        "You are the Synthesizer. Read the user prompt and the four agent drafts. "
        "Merge the best ideas, resolve conflicts, and return ONE polished answer. "
        "Be decisive and concise. Only output the final answer—no preamble."
    )
    resp = await client.responses.create(
        model=model,
        instructions=synth_instructions,
        input=f"USER PROMPT:\n{user_prompt.strip()}\n\nPANEL RESPONSES:\n{stitched}",
        reasoning=SYNTH_REASONING,
        text=SYNTH_TEXT,
        max_output_tokens=SYNTH_MAX_TOKENS,
    )
    return _extract_output_text(resp)


# ------------------ UI Rendering ------------------

def fmt_elapsed(sec: float) -> str:
    return f"{int(sec//60):02d}:{int(sec%60):02d}"


def render_dashboard(states: List[AgentState], synth: Optional[AgentState]) -> Panel:
    tbl = Table(show_header=True, header_style="bold", expand=True, pad_edge=False)
    tbl.add_column("Agent", no_wrap=True)
    tbl.add_column("Model", no_wrap=True)
    tbl.add_column("Status", ratio=1)
    tbl.add_column("Elapsed", no_wrap=True)

    for st in states:
        if st.ok is None:
            status_cell = Group(Spinner("dots", text=" running"))
        elif st.ok:
            status_cell = Text(" done ✓", style="green")
        else:
            status_cell = Text(f" error ✗ {st.error or ''}", style="red")
        tbl.add_row(st.name, st.model, status_cell, fmt_elapsed(st.elapsed))

    if synth:
        if synth.ok is None:
            status_cell = Group(Spinner("bouncingBar", text=" synthesizing"))
        elif synth.ok:
            status_cell = Text(" finalizing ✓", style="green")
        else:
            status_cell = Text(f" error ✗ {synth.error or ''}", style="red")
        tbl.add_row(synth.name, synth.model, status_cell, fmt_elapsed(synth.elapsed))

    title = Text("Multi-Agent Orchestrator (GPT-5)", style="bold")
    return Panel(tbl, title=title, border_style="cyan")


# ------------------ Logging ------------------

def build_full_trace(user_prompt: str, states: List[AgentState], synth: AgentState) -> str:
    lines = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"[Run @ {ts}]")
    lines.append("")
    lines.append("=== USER PROMPT ===")
    lines.append(user_prompt.strip())
    lines.append("")
    lines.append("=== AGENT DRAFTS ===")
    for st in states:
        lines.append(f"\n--- {st.name} ({st.model}) | elapsed {fmt_elapsed(st.elapsed)} | "
                     f"status: {'ok' if st.ok else 'error' if st.ok is False else 'running'} ---")
        if st.ok and st.output_text:
            lines.append(st.output_text)
        elif st.error:
            lines.append(f"[ERROR] {st.error}")
        else:
            lines.append("[no output]")
    lines.append("")
    lines.append("=== FINAL ANSWER ===")
    lines.append(synth.output_text or "")
    lines.append("")
    return "\n".join(lines)


def write_trace_to_file(content: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = f"gpt5_trace_{ts}.txt"
    path = os.path.join(os.getcwd(), fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ------------------ Orchestrator ------------------

async def orchestrate(user_prompt: str, log_all: bool = False) -> str:
    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    states: List[AgentState] = [
        AgentState(name="Planner",   model=AGENT_MODELS[0]),
        AgentState(name="Explainer", model=AGENT_MODELS[1]),
        AgentState(name="Optimizer", model=AGENT_MODELS[2]),
        AgentState(name="Skeptic",   model=AGENT_MODELS[3]),
    ]
    synth_state = AgentState(name="Synthesizer", model=SYNTH_MODEL)

    async def _run_agent(i: int):
        st = states[i]
        try:
            out = await call_agent(client, AGENT_ROLES[i], st.model, user_prompt)
            st.output_text = out
            st.ok = True
        except Exception as e:
            st.ok = False
            st.error = str(e)
        finally:
            st.ended_at = time.time()

    tasks = [asyncio.create_task(_run_agent(i)) for i in range(4)]

    # Live TUI while agents run and during synthesis
    with Live(render_dashboard(states, None), console=console, refresh_per_second=12) as live:
        while any(st.ok is None for st in states):
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, None))
        await asyncio.gather(*tasks, return_exceptions=True)

        synth_state.started_at = time.time()
        live.update(render_dashboard(states, synth_state))
        try:
            panel_map: Dict[str, Tuple[str, str]] = {st.name: (st.model, st.output_text or "") for st in states}
            final = await call_synth(client, SYNTH_MODEL, user_prompt, panel_map)
            synth_state.ok = True
            synth_state.output_text = final
        except Exception as e:
            synth_state.ok = False
            synth_state.error = str(e)
            synth_state.output_text = ""
        finally:
            synth_state.ended_at = time.time()
            live.update(render_dashboard(states, synth_state))
            await asyncio.sleep(0.35)

    # Optional: silent dump of the full trace to a TXT file
    if log_all:
        try:
            trace = build_full_trace(user_prompt, states, synth_state)
            write_trace_to_file(trace)
        except Exception:
            # Silent failure by design—no extra console noise
            pass

    return synth_state.output_text or ""


# ------------------ Settings Menu ------------------

def settings_menu() -> None:
    global LOG_ALL_TO_FILE
    while True:
        console.print("\n[bold cyan]Settings[/bold cyan]")
        status = "[green]ON[/green]" if LOG_ALL_TO_FILE else "[red]OFF[/red]"
        console.print(f"  1) Log all model responses to TXT file: {status}")
        console.print("  t) Toggle   q) Back\n")
        choice = input("> ").strip().lower()
        if choice in ("1", "t", "toggle"):
            LOG_ALL_TO_FILE = not LOG_ALL_TO_FILE
        elif choice in ("q", "b", "back", ""):
            break


# ------------------ CLI ------------------

def main():
    global LOG_ALL_TO_FILE
    while True:
        prompt = input("Enter your prompt (or /settings, or blank to quit): ").strip()
        if not prompt:
            break
        if prompt.startswith("/settings"):
            settings_menu()
            continue

        # Run once and print ONLY the final synthesized answer
        final_answer = asyncio.run(orchestrate(prompt, log_all=LOG_ALL_TO_FILE))
        print(final_answer)

        # Single-shot run; comment the next line if you want to loop for multiple prompts
        break


if __name__ == "__main__":
    main()
