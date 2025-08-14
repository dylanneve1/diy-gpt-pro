# File: multiworker/orchestrator.py
import asyncio
import time
from typing import Dict, List

from .types import AgentState
from .ui import Live, render_dashboard, console
from . import config
from .openai_calls import call_worker, call_synth, get_retry_stats
from .logging_trace import build_full_trace, write_trace_to_file

def _compute_stats(states: List[AgentState], synth: AgentState | None, turn_start: float) -> dict:
    now = time.time()
    elapsed = (synth.ended_at if synth and synth.ended_at else now) - turn_start

    total = len(states)
    done = sum(1 for s in states if s.ok is True)
    err  = sum(1 for s in states if s.ok is False)
    run  = total - done - err

    # worker times for finished ones (fallback to current elapsed for running)
    worker_times = [(s.ended_at or now) - s.started_at for s in states]
    avg = (sum(worker_times) / len(worker_times)) if worker_times else 0.0
    mx  = max(worker_times) if worker_times else 0.0

    rstats = get_retry_stats(reset=False)

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
    }

async def run_turn(client, history: List[Dict[str, str]]) -> str:
    # Reset retry telemetry for this turn
    get_retry_stats(reset=True)
    turn_start = time.time()

    states: List[AgentState] = [
        AgentState(name=config.WORKER_NAMES[i], model=config.CURRENT_MODEL)
        for i in range(config.N_WORKERS)
    ]
    synth_state = AgentState(name="Synthesizer", model=config.CURRENT_MODEL)

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

    tasks = [asyncio.create_task(_run_worker(i)) for i in range(config.N_WORKERS)]

    # Live UI while workers run and synthesize
    with Live(render_dashboard(states, None, _compute_stats(states, None, turn_start)), console=console, refresh_per_second=14) as live:
        # Update while workers are running
        while any(st.ok is None for st in states):
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, None, _compute_stats(states, None, turn_start)))
        await asyncio.gather(*tasks, return_exceptions=True)

        # Start synthesizer and continuously refresh elapsed time while it runs
        synth_state.started_at = time.time()
        live.update(render_dashboard(states, synth_state, _compute_stats(states, synth_state, turn_start)))

        async def _do_synth():
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

        synth_task = asyncio.create_task(_do_synth())
        while not synth_task.done():
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, synth_state, _compute_stats(states, synth_state, turn_start)))
        await synth_task
        live.update(render_dashboard(states, synth_state, _compute_stats(states, synth_state, turn_start)))

    if config.LOG_ALL_TO_FILE:
        try:
            user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
            trace = build_full_trace(user_msg, states, synth_state, history)
            write_trace_to_file(trace)
        except Exception:
            pass

    return synth_state.output_text or ""
