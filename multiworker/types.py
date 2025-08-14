# File: multiworker/types.py
from dataclasses import dataclass, field
import time
from typing import Optional

@dataclass
class AgentState:
    name: str
    model: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    ok: Optional[bool] = None
    error: Optional[str] = None
    output_text: Optional[str] = None

    @property
    def elapsed(self) -> float:
        end = self.ended_at if self.ended_at else time.time()
        return max(0.0, end - self.started_at)
