# File: multiworker/logging_trace.py
import os
import time
from .ui import fmt_elapsed
from .types import AgentState

def build_full_trace(user_msg: str, states: list[AgentState], synth: AgentState, history: list[dict]) -> str:
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
