#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from openai import AsyncOpenAI

from rich.live import Live
from rich.table import Table
from rich.console import Console, Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

console = Console()

# ------------------ Config ------------------

CURRENT_MODEL = "gpt-5"       # default; switch via /settings (gpt-5 | gpt-5-mini | gpt-5-nano)
MODEL_CHOICES = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]

N_WORKERS = 4
WORKER_NAMES = [f"Worker-{i+1}" for i in range(N_WORKERS)]

REASONING_LEVEL = "medium"    # minimal | low | medium | high (switch via /settings)
TEXT_VERBOSITY = "low"

WORKER_INSTRUCTION = (
    "You are a Worker. Read the chat so far and the latest user message. "
    "Use brief internal reasoning, then return a complete, correct, and concise draft answer. "
    "No preamble; focus on the solution."
)

SYNTH_INSTRUCTION = (
    "You are the Synthesizer. Read the chat so far and the four Worker drafts. "
    "Merge the best ideas, resolve conflicts, and produce ONE polished answer. "
    "Be decisive, accurate, and concise. Output only the final answer—no preamble."
)

LOG_ALL_TO_FILE: bool = False

SESS_DIR = Path("sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)


# ------------------ State ------------------

@dataclass
class AgentState:
    name: str
    model: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    ok: Optional[bool] = None
    error: Optional[str] = None
    output_text: Optional[str] = None

    @property
    def elapsed(self) -> float:
        end = self.ended_at if self.ended_at else time.time()
        return max(0.0, end - self.started_at)


# ------------------ Helpers ------------------

def reasoning_dict() -> Dict[str, str]:
    return {"effort": REASONING_LEVEL}

def text_dict() -> Dict[str, str]:
    return {"verbosity": TEXT_VERBOSITY}

def _extract_output_text(resp) -> str:
    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
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


# ------------------ OpenAI Calls ------------------

async def call_worker(client: AsyncOpenAI, history: List[Dict[str, str]]) -> str:
    resp = await client.responses.create(
        model=CURRENT_MODEL,
        instructions=WORKER_INSTRUCTION,
        input=history,
        reasoning=reasoning_dict(),
        text=text_dict(),
    )
    return _extract_output_text(resp)

async def call_synth(client: AsyncOpenAI, history: List[Dict[str, str]], drafts: Dict[str, str]) -> str:
    stitched = "\n\n".join(f"### {name}\n{text.strip()}" for name, text in drafts.items())
    synth_input = history + [{"role": "assistant", "content": "WORKER DRAFTS:\n" + stitched}]
    resp = await client.responses.create(
        model=CURRENT_MODEL,
        instructions=SYNTH_INSTRUCTION,
        input=synth_input,
        reasoning=reasoning_dict(),
        text=text_dict(),
    )
    return _extract_output_text(resp)


# ------------------ UI Rendering ------------------

def fmt_elapsed(sec: float) -> str:
    return f"{int(sec//60):02d}:{int(sec%60):02d}"

def render_dashboard(states: List[AgentState], synth: Optional[AgentState]) -> Panel:
    tbl = Table(show_header=True, header_style="bold", expand=True, pad_edge=False)
    tbl.add_column("Worker", no_wrap=True)
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

    title = Text(f"Multi-Worker Orchestrator ({CURRENT_MODEL}, reasoning={REASONING_LEVEL})", style="bold")
    return Panel(tbl, title=title, border_style="cyan")


# ------------------ Logging ------------------

def build_full_trace(user_msg: str, states: List[AgentState], synth: AgentState, history: List[Dict[str, str]]) -> str:
    lines = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"[Run @ {ts}]")
    lines.append("")
    lines.append("=== CHAT HISTORY BEFORE THIS TURN ===")
    for m in history[:-1]:
        lines.append(f"{m['role']}: {m['content']}")
    lines.append("")
    lines.append("=== LATEST USER MESSAGE ===")
    lines.append(user_msg.strip())
    lines.append("")
    lines.append("=== WORKER DRAFTS ===")
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


# ------------------ Sessions ------------------

def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", name).strip("_") or "session"

def list_sessions() -> List[str]:
    return sorted([p.stem for p in SESS_DIR.glob("*.json")])

def save_session(name: str, history: List[Dict[str, str]]) -> str:
    fname = _slug(name) + ".json"
    path = SESS_DIR / fname
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"messages": history}, f, ensure_ascii=False, indent=2)
    return str(path)

def load_session(name: str) -> Optional[List[Dict[str, str]]]:
    fname = _slug(name) + ".json"
    path = SESS_DIR / fname
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    msgs = data.get("messages", [])
    out = []
    for m in msgs:
        if isinstance(m, dict) and "role" in m and "content" in m:
            out.append({"role": str(m["role"]), "content": str(m["content"])})
    return out


# ------------------ Orchestrator (per-turn) ------------------

async def run_turn(client: AsyncOpenAI, history: List[Dict[str, str]]) -> str:
    states: List[AgentState] = [AgentState(name=WORKER_NAMES[i], model=CURRENT_MODEL) for i in range(N_WORKERS)]
    synth_state = AgentState(name="Synthesizer", model=CURRENT_MODEL)

    async def _run_worker(i: int):
        st = states[i]
        try:
            out = await call_worker(client, history)
            st.output_text = out
            st.ok = True
        except Exception as e:
            st.ok = False
            st.error = str(e)
        finally:
            st.ended_at = time.time()

    tasks = [asyncio.create_task(_run_worker(i)) for i in range(N_WORKERS)]

    with Live(render_dashboard(states, None), console=console, refresh_per_second=14) as live:
        while any(st.ok is None for st in states):
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, None))
        await asyncio.gather(*tasks, return_exceptions=True)

        synth_state.started_at = time.time()
        live.update(render_dashboard(states, synth_state))
        try:
            drafts_map: Dict[str, str] = {st.name: (st.output_text or "") for st in states}
            final = await call_synth(client, history, drafts_map)
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

    if LOG_ALL_TO_FILE:
        try:
            user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
            trace = build_full_trace(user_msg, states, synth_state, history)
            write_trace_to_file(trace)
        except Exception:
            pass

    return synth_state.output_text or ""


# ------------------ Settings Menu ------------------

def settings_menu() -> None:
    global LOG_ALL_TO_FILE, REASONING_LEVEL, CURRENT_MODEL
    levels = ["minimal", "low", "medium", "high"]
    while True:
        console.print("\n[bold cyan]Settings[/bold cyan]")
        log_status = "[green]ON[/green]" if LOG_ALL_TO_FILE else "[red]OFF[/red]"
        console.print(f"  1) Log all model responses to TXT file: {log_status}")
        console.print(f"  2) Reasoning level: [bold]{REASONING_LEVEL}[/bold] (choices: {', '.join(levels)})")
        console.print(f"  3) Model: [bold]{CURRENT_MODEL}[/bold] (choices: {', '.join(MODEL_CHOICES)})")
        console.print("  t) Toggle logging   r) Set reasoning   m) Set model   q) Back\n")
        choice = input("> ").strip().lower()
        if choice in ("1", "t", "toggle"):
            LOG_ALL_TO_FILE = not LOG_ALL_TO_FILE
        elif choice in ("2", "r", "reasoning"):
            new_level = input("Enter reasoning level (minimal|low|medium|high): ").strip().lower()
            if new_level in levels:
                REASONING_LEVEL = new_level
                console.print(f"[green]Reasoning set to {REASONING_LEVEL}[/green]")
            else:
                console.print("[red]Invalid level.[/red]")
        elif choice in ("3", "m", "model"):
            new_model = input(f"Enter model ({', '.join(MODEL_CHOICES)}): ").strip()
            if new_model in MODEL_CHOICES:
                CURRENT_MODEL = new_model
                console.print(f"[green]Model set to {CURRENT_MODEL}[/green]")
            else:
                console.print("[red]Invalid model.[/red]")
        elif choice in ("q", "b", "back", ""):
            break


# ------------------ CLI Loop ------------------

def main():
    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    history: List[Dict[str, str]] = []

    console.print("[bold]Multi-Worker Orchestrator[/bold] — commands: /list, /save <n>, /load <n>, /settings, /exit")

    while True:
        user_in = input("\nYou: ").strip()
        if not user_in:
            continue

        if user_in.startswith("/exit"):
            break

        if user_in.startswith("/settings"):
            settings_menu()
            continue

        if user_in.startswith("/list"):
            items = list_sessions()
            if items:
                console.print("[bold cyan]Saved sessions:[/bold cyan] " + ", ".join(items))
            else:
                console.print("[dim]No saved sessions.[/dim]")
            continue

        if user_in.startswith("/save"):
            parts = user_in.split(maxsplit=1)
            if len(parts) < 2:
                console.print("[red]Usage: /save <name>[/red]")
                continue
            path = save_session(parts[1], history)
            console.print(f"[green]Saved[/green] → {path}")
            continue

        if user_in.startswith("/load"):
            parts = user_in.split(maxsplit=1)
            if len(parts) < 2:
                console.print("[red]Usage: /load <name>[/red]")
                continue
            msgs = load_session(parts[1])
            if msgs is None:
                console.print("[red]Not found.[/red]")
                continue
            history = msgs
            console.print(f"[green]Loaded[/green] session '{_slug(parts[1])}' with {len(history)} messages.")
            continue

        history.append({"role": "user", "content": user_in})
        final_answer = asyncio.run(run_turn(client, history))
        print(final_answer)
        history.append({"role": "assistant", "content": final_answer})

    console.print("[dim]Bye.[/dim]")


if __name__ == "__main__":
    main()
