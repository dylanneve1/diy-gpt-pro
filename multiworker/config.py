# File: multiworker/config.py
from pathlib import Path
import json

# ------------------ Paths ------------------
SETTINGS_PATH = Path("settings.json")
SESS_DIR = Path("sessions")
SESS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------ Defaults ------------------
MODEL_CHOICES = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]
CURRENT_MODEL: str = "gpt-5"                      # default; can be changed in /settings

REASONING_LEVEL: str = "medium"                   # minimal | low | medium | high
TEXT_VERBOSITY: str = "low"                       # keep concise; not exposed in /settings (yet)

# Parallel workers
N_WORKERS: int = 4
WORKER_NAMES = [f"Worker-{i+1}" for i in range(N_WORKERS)]

# Retry policy
RETRY_MAX: int = 5
RETRY_DELAY_SEC: int = 5

# Logging
LOG_ALL_TO_FILE: bool = False

# Running token totals (accumulate across turns; persisted in session files via /save)
RUNNING_TOKENS: dict = {"input": 0, "output": 0, "total": 0}

# ------------------ System instructions ------------------
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

# ------------------ Helpers ------------------
def reasoning_dict():
    return {"effort": REASONING_LEVEL}

def text_dict():
    return {"verbosity": TEXT_VERBOSITY}

# ------------------ Persistence (settings.json) ------------------
def _validate_settings(data: dict) -> dict:
    """Coerce/validate incoming settings dict; fall back to current globals if invalid."""
    global CURRENT_MODEL, REASONING_LEVEL, TEXT_VERBOSITY, LOG_ALL_TO_FILE, N_WORKERS, RETRY_MAX, RETRY_DELAY_SEC

    out = {}

    # CURRENT_MODEL
    model = data.get("CURRENT_MODEL", CURRENT_MODEL)
    out["CURRENT_MODEL"] = model if model in MODEL_CHOICES else CURRENT_MODEL

    # REASONING_LEVEL
    allowed_levels = {"minimal", "low", "medium", "high"}
    lvl = str(data.get("REASONING_LEVEL", REASONING_LEVEL)).lower()
    out["REASONING_LEVEL"] = lvl if lvl in allowed_levels else REASONING_LEVEL

    # TEXT_VERBOSITY (not exposed in UI yet, but persist if present)
    allowed_verb = {"low", "medium", "high"}
    verb = str(data.get("TEXT_VERBOSITY", TEXT_VERBOSITY)).lower()
    out["TEXT_VERBOSITY"] = verb if verb in allowed_verb else TEXT_VERBOSITY

    # LOG_ALL_TO_FILE
    out["LOG_ALL_TO_FILE"] = bool(data.get("LOG_ALL_TO_FILE", LOG_ALL_TO_FILE))

    # N_WORKERS (1..8)
    try:
        n = int(data.get("N_WORKERS", N_WORKERS))
        out["N_WORKERS"] = max(1, min(8, n))
    except Exception:
        out["N_WORKERS"] = N_WORKERS

    # Retry policy (bounds)
    try:
        rmax = int(data.get("RETRY_MAX", RETRY_MAX))
        out["RETRY_MAX"] = max(1, min(10, rmax))
    except Exception:
        out["RETRY_MAX"] = RETRY_MAX

    try:
        rdelay = float(data.get("RETRY_DELAY_SEC", RETRY_DELAY_SEC))
        out["RETRY_DELAY_SEC"] = max(1.0, min(60.0, rdelay))
    except Exception:
        out["RETRY_DELAY_SEC"] = RETRY_DELAY_SEC

    return out

def _apply_settings(valid: dict) -> None:
    """Write validated settings into module globals and recompute derived values."""
    global CURRENT_MODEL, REASONING_LEVEL, TEXT_VERBOSITY, LOG_ALL_TO_FILE
    global N_WORKERS, WORKER_NAMES, RETRY_MAX, RETRY_DELAY_SEC

    CURRENT_MODEL   = valid["CURRENT_MODEL"]
    REASONING_LEVEL = valid["REASONING_LEVEL"]
    TEXT_VERBOSITY  = valid["TEXT_VERBOSITY"]
    LOG_ALL_TO_FILE = valid["LOG_ALL_TO_FILE"]
    N_WORKERS       = valid["N_WORKERS"]
    RETRY_MAX       = int(valid["RETRY_MAX"])
    RETRY_DELAY_SEC = float(valid["RETRY_DELAY_SEC"])
    WORKER_NAMES[:] = [f"Worker-{i+1}" for i in range(N_WORKERS)]

def to_dict() -> dict:
    """Export current settings to a JSON-serializable dict (not session tokens)."""
    return {
        "CURRENT_MODEL": CURRENT_MODEL,
        "MODEL_CHOICES": MODEL_CHOICES,           # informational
        "REASONING_LEVEL": REASONING_LEVEL,
        "TEXT_VERBOSITY": TEXT_VERBOSITY,
        "LOG_ALL_TO_FILE": LOG_ALL_TO_FILE,
        "N_WORKERS": N_WORKERS,
        "RETRY_MAX": RETRY_MAX,
        "RETRY_DELAY_SEC": RETRY_DELAY_SEC,
    }

def load_settings() -> None:
    """Load settings.json if present and apply them."""
    if not SETTINGS_PATH.exists():
        return
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        valid = _validate_settings(data or {})
        _apply_settings(valid)
    except Exception:
        pass

def save_settings() -> None:
    """Write current settings to settings.json (atomic-ish)."""
    data = to_dict()
    try:
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
    except Exception:
        pass

# Load persisted settings on import
load_settings()
