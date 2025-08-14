# File: multiworker/orchestrator.py
import asyncio
import time
from typing import Dict, List

from .types import AgentState
from .ui import Live, render_dashboard, console
from . import config
from .openai_calls import call_worker, call_synth
from .logging_trace import build_full_trace, write_trace_to_file

async def run_turn(client, history: List[Dict[str, str]]) -> str:
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
    with Live(render_dashboard(states, None), console=console, refresh_per_second=14) as live:
        # Update while workers are running
        while any(st.ok is None for st in states):
            await asyncio.sleep(0.08)
            live.update(render_dashboard(states, None))
        await asyncio.gather(*tasks, return_exceptions=True)

        # Start synthesizer and continuously refresh elapsed time while it runs
        synth_state.started_at = time.time()
        live.update(render_dashboard(states, synth_state))

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
            # elapsed updates because AgentState.elapsed uses current time when ended_at is None
            live.update(render_dashboard(states, synth_state))
        await synth_task  # propagate any exceptions already handled; ensures completion
        live.update(render_dashboard(states, synth_state))

    if config.LOG_ALL_TO_FILE:
        try:
            user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
            trace = build_full_trace(user_msg, states, synth_state, history)
            write_trace_to_file(trace)
        except Exception:
            pass

    return synth_state.output_text or ""
