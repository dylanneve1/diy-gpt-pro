# File: multiworker/orchestrator.py
import asyncio
import time
from typing import Dict, List

from .types import AgentState
from .ui import Live, render_dashboard, console
from . import config
from .openai_calls import call_worker, call_synth, get_retry_stats
from .logging_trace import build_full_trace, write_trace_to_file

def _compute_stats(
    states: List[AgentState],
    synth: AgentState | None,
    turn_start: float,
    tokens_turn: Dict[str, int],
    tokens_base: Dict[str, int],
) -> dict:
    """
    Compute live stats for footer.
    - tokens_turn: per-turn usage so far
    - tokens_base: running totals at turn start (persisted across turns)
    """
    now = time.time()
    elapsed = (synth.ended_at if synth and synth.ended_at else now) - turn_start

    total = len(states)
    done = sum(1 for s in states if s.ok is True)
    err  = sum(1 for s in states if s.ok is False)
    run  = total - done - err

    worker_times = [(s.ended_at or now) - s.started_at for s in states]
    avg = (sum(worker_times) / len(worker_times)) if worker_times else 0.0
    mx  = max(worker_times) if worker_times else 0.0

    rstats = get_retry_stats(reset=False)

    # Running totals = baseline at turn start + tokens accumulated this turn
    run_in  = int(tokens_base.get("input", 0))  + int(tokens_turn.get("input", 0))
    run_out = int(tokens_base.get("output", 0)) + int(tokens_turn.get("output", 0))
    run_tot = int(tokens_base.get("total", 0))  + int(tokens_turn.get("total", 0))

    return {
        "elapsed": max(0.0, elapsed),
        "workers_total": total,
        "workers_done": done,
        "workers_err": err,
        "workers_run": run,
        "worker_avg": avg,
        "worker_max": mx,
        "retries_total": rstats.get("retries_total", 0),
        "retry_events": rstats.get("retry_events", 0),
        # Per-turn tokens so far
        "tokens_input": int(tokens_turn.get("input", 0)),
        "tokens_output": int(tokens_turn.get("output", 0)),
        "tokens_total": int(tokens_turn.get("total", 0)),
        # Running totals (baseline + this turn)
        "tokens_run_input": run_in,
        "tokens_run_output": run_out,
        "tokens_run_total": run_tot,
    }

async def run_turn(client, history: List[Dict[str, str]]) -> str:
    # Reset retry telemetry for this turn
    get_retry_stats(reset=True)
    turn_start = time.time()

    # Snapshot running totals at turn start (for stable live display)
    tokens_base = {
        "input":  int(config.RUNNING_TOKENS.get("input", 0)),
        "output": int(config.RUNNING_TOKENS.get("output", 0)),
        "total":  int(config.RUNNING_TOKENS.get("total", 0)),
    }

    # Per-turn token usage accumulators
    tokens_turn = {"input": 0, "output": 0, "total": 0}
    token_lock = asyncio.Lock()

    states: List[AgentState] = [
        AgentState(name=config.WORKER_NAMES[i], model=config.CURRENT_MODEL)
        for i in range(config.N_WORKERS)
    ]
    synth_state = AgentState(name="Synthesizer", model=config.CURRENT_MODEL)

    async def _run_worker(i: int):
        st = states[i]
        try:
            text, usage = await call_worker(client, history)
            st.output_text = text
            st.ok = True
            st.tokens = usage  # optional attribute for debugging/logging
            async with token_lock:
                tokens_turn["input"]  += int(usage.get("input", 0))
                tokens_turn["output"] += int(usage.get("output", 0))
                tokens_turn["total"]  += int(usage.get("total", 0))
        except Exception as e:
            st.ok = False
            st.error = str(e)
        finally:
            st.ended_at = time.time()

    tasks = [asyncio.create_task(_run_worker(i)) for i in range(config.N_WORKERS)]

    # Live UI while workers run and synthesize
    with Live(
        render_dashboard(states, None, _compute_stats(states, None, turn_start, tokens_turn, tokens_base)),
        console=console,
        refresh_per_second=14
    ) as live:
        # Update while workers are running
        while any(st.ok is None for st in states):
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, None, _compute_stats(states, None, turn_start, tokens_turn, tokens_base)))
        await asyncio.gather(*tasks, return_exceptions=True)

        # Start synthesizer and continuously refresh elapsed time while it runs
        synth_state.started_at = time.time()
        live.update(render_dashboard(states, synth_state, _compute_stats(states, synth_state, turn_start, tokens_turn, tokens_base)))

        async def _do_synth():
            try:
                drafts_map: Dict[str, str] = {st.name: (st.output_text or "") for st in states}
                final, usage = await call_synth(client, history, drafts_map)
                synth_state.ok = True
                synth_state.output_text = final
                async with token_lock:
                    tokens_turn["input"]  += int(usage.get("input", 0))
                    tokens_turn["output"] += int(usage.get("output", 0))
                    tokens_turn["total"]  += int(usage.get("total", 0))
            except Exception as e:
                synth_state.ok = False
                synth_state.error = str(e)
                synth_state.output_text = ""
            finally:
                synth_state.ended_at = time.time()

        synth_task = asyncio.create_task(_do_synth())
        while not synth_task.done():
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, synth_state, _compute_stats(states, synth_state, turn_start, tokens_turn, tokens_base)))
        await synth_task
        live.update(render_dashboard(states, synth_state, _compute_stats(states, synth_state, turn_start, tokens_turn, tokens_base)))

    # Update running totals in config after the turn completes
    config.RUNNING_TOKENS["input"]  += tokens_turn.get("input", 0)
    config.RUNNING_TOKENS["output"] += tokens_turn.get("output", 0)
    config.RUNNING_TOKENS["total"]  += tokens_turn.get("total", 0)

    if config.LOG_ALL_TO_FILE:
        try:
            user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
            trace = build_full_trace(user_msg, states, synth_state, history)
            write_trace_to_file(trace)
        except Exception:
            pass

    return synth_state.output_text or ""
