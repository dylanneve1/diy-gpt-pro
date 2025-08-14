# File: multiworker/sessions.py
import json
from typing import List, Optional, Tuple
from . import config
import re

def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", name).strip("_") or "session"

def list_sessions() -> List[str]:
    return sorted([p.stem for p in config.SESS_DIR.glob("*.json")])

def save_session(name: str, history: list[dict], running_tokens: dict) -> str:
    """
    Save the current chat history AND running token totals to sessions/<name>.json
    running_tokens should be a dict like {"input": int, "output": int, "total": int}
    """
    fname = slug(name) + ".json"
    path = config.SESS_DIR / fname
    payload = {
        "messages": history,
        "running_tokens": {
            "input": int(running_tokens.get("input", 0)),
            "output": int(running_tokens.get("output", 0)),
            "total": int(running_tokens.get("total", 0)),
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)

def load_session(name: str) -> Optional[Tuple[list[dict], dict]]:
    """
    Load a session file. Returns (messages, running_tokens) or None if missing.
    For older files without running_tokens, returns zeros.
    """
    fname = slug(name) + ".json"
    path = config.SESS_DIR / fname
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    msgs_raw = data.get("messages", [])
    messages: list[dict] = []
    for m in msgs_raw:
        if isinstance(m, dict) and "role" in m and "content" in m:
            messages.append({"role": str(m["role"]), "content": str(m["content"])})

    tokens_raw = data.get("running_tokens", {})
    running_tokens = {
        "input": int(tokens_raw.get("input", 0) or 0),
        "output": int(tokens_raw.get("output", 0) or 0),
        "total": int(tokens_raw.get("total", 0) or 0),
    }

    return messages, running_tokens
