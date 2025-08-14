# File: multiworker/ui.py
from rich.live import Live
from rich.table import Table
from rich.console import Console, Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from rich.align import Align

from .types import AgentState
from . import config

console = Console()

def fmt_elapsed(sec: float) -> str:
    return f"{int(sec//60):02d}:{int(sec%60):02d}"

def _stats_footer(stats: dict) -> Panel:
    """
    Compact stats footer panel.
    Keys (all optional, default 0):
      elapsed, workers_done, workers_err, workers_run, workers_total,
      worker_avg, worker_max,
      retries_total, retry_events,
      tokens_input, tokens_output, tokens_total,            # this turn
      tokens_run_input, tokens_run_output, tokens_run_total # running (Σ)
    """
    footer = Table.grid(expand=True)
    footer.add_column(ratio=1)
    footer.add_column(ratio=1)
    footer.add_column(ratio=1)

    left = Text.assemble(
        ("Elapsed: ", "bold"),
        fmt_elapsed(stats.get("elapsed", 0.0)),
        "   ",
        ("Model: ", "bold"),
        f"{config.CURRENT_MODEL}",
        "   ",
        ("Reasoning: ", "bold"),
        f"{config.REASONING_LEVEL}",
    )

    mid = Text.assemble(
        ("Workers: ", "bold"),
        f"{stats.get('workers_done', 0)}/{stats.get('workers_total', 0)} done",
        f", {stats.get('workers_err', 0)} err",
        f", {stats.get('workers_run', 0)} run",
        "   ",
        ("Avg: ", "bold"),
        fmt_elapsed(stats.get("worker_avg", 0.0)),
        "   ",
        ("Max: ", "bold"),
        fmt_elapsed(stats.get("worker_max", 0.0)),
    )

    # Tokens: show per-turn and cumulative Σ side by side
    t_in  = stats.get("tokens_input", 0)
    t_out = stats.get("tokens_output", 0)
    t_tot = stats.get("tokens_total", 0)

    r_in  = stats.get("tokens_run_input", 0)
    r_out = stats.get("tokens_run_output", 0)
    r_tot = stats.get("tokens_run_total", 0)

    right = Text.assemble(
        ("Retries: ", "bold"),
        f"{stats.get('retries_total', 0)}",
        "  (events ",
        f"{stats.get('retry_events', 0)}",
        ")   ",
        ("Tokens ", "bold"),
        f"turn in:{t_in} / out:{t_out} / total:{t_tot}",
        "   ",
        ("Σ ", "bold"),
        f"in:{r_in} / out:{r_out} / total:{r_tot}",
    )

    footer.add_row(left, mid, Align.right(right))
    return Panel(footer, border_style="magenta", title="Stats", title_align="left")

def render_dashboard(states: list[AgentState], synth: AgentState | None, stats: dict | None = None) -> Panel:
    # Main table
    tbl = Table(
        show_header=True,
        header_style="bold",
        expand=True,
        pad_edge=False,
        box=None,
    )
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

    title_text = Text.assemble(
        ("Multi-Worker Orchestrator", "bold"),
        ("  (",),
        (f"{config.CURRENT_MODEL}", "cyan"),
        (", reasoning=",),
        (f"{config.REASONING_LEVEL}", "cyan"),
        (")",),
    )

    # Group table + optional stats footer into one panel
    if stats is not None:
        content = Group(tbl, _stats_footer(stats))
    else:
        content = Group(tbl)

    return Panel(content, title=title_text, border_style="cyan")
