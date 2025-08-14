# File: multiworker/sessions.py
import json
from typing import List, Optional
from . import config
import re

def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", name).strip("_") or "session"

def list_sessions() -> List[str]:
    return sorted([p.stem for p in config.SESS_DIR.glob("*.json")])

def save_session(name: str, history: list[dict]) -> str:
    fname = slug(name) + ".json"
    path = config.SESS_DIR / fname
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"messages": history}, f, ensure_ascii=False, indent=2)
    return str(path)

def load_session(name: str) -> Optional[list[dict]]:
    fname = slug(name) + ".json"
    path = config.SESS_DIR / fname
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
