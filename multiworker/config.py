# File: multiworker/config.py
from pathlib import Path

# Model & reasoning defaults (mutable at runtime via /settings)
CURRENT_MODEL: str = "gpt-5"                       # choices below
MODEL_CHOICES = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]

REASONING_LEVEL: str = "medium"                    # minimal | low | medium | high
TEXT_VERBOSITY: str = "low"

# Parallel workers
N_WORKERS: int = 4
WORKER_NAMES = [f"Worker-{i+1}" for i in range(N_WORKERS)]

# Retry policy
RETRY_MAX: int = 5
RETRY_DELAY_SEC: int = 5

# Logging
LOG_ALL_TO_FILE: bool = False

# Sessions directory
SESS_DIR = Path("sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)

# System instructions
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

def reasoning_dict():
    return {"effort": REASONING_LEVEL}

def text_dict():
    return {"verbosity": TEXT_VERBOSITY}
