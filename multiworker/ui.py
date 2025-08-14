# File: multiworker/ui.py
from rich.live import Live
from rich.table import Table
from rich.console import Console, Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from .types import AgentState
from . import config

console = Console()

def fmt_elapsed(sec: float) -> str:
    return f"{int(sec//60):02d}:{int(sec%60):02d}"

def render_dashboard(states: list[AgentState], synth: AgentState | None) -> Panel:
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

    title = Text(f"Multi-Worker Orchestrator ({config.CURRENT_MODEL}, reasoning={config.REASONING_LEVEL})", style="bold")
    return Panel(tbl, title=title, border_style="cyan")

__all__ = ["console", "Live", "render_dashboard", "fmt_elapsed"]
