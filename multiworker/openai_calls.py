# File: multiworker/openai_calls.py
import asyncio
import re
import math
from typing import Dict, List, Tuple
from openai import AsyncOpenAI

from . import config

# ---------- Retry telemetry (for Stats footer) ----------
_RETRY_COUNT = 0                 # total number of retry attempts (sleeps)
_RETRY_EVENTS = 0                # number of requests that required at least one retry
_RETRY_DELAYS: list[float] = []  # seconds slept per retry


def get_retry_stats(reset: bool = False) -> dict:
    """Return aggregate retry telemetry. Optionally reset after reading."""
    global _RETRY_COUNT, _RETRY_EVENTS, _RETRY_DELAYS
    stats = {
        "retries_total": _RETRY_COUNT,
        "retry_events": _RETRY_EVENTS,
        "delays": list(_RETRY_DELAYS),
    }
    if reset:
        _RETRY_COUNT = 0
        _RETRY_EVENTS = 0
        _RETRY_DELAYS.clear()
    return stats


def _extract_output_text(resp) -> str:
    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
    try:
        chunks = []
        for item in getattr(resp, "output", []):
            for block in getattr(item, "content", []):
                if getattr(block, "type", None) == "output_text":
                    chunks.append(getattr(block, "text", ""))
        if chunks:
            return "".join(chunks).strip()
    except Exception:
        pass
    return str(resp)


def _extract_usage(resp) -> Dict[str, int]:
    """
    Try to pull token usage from response.
    Returns dict with keys: input, output, total. Falls back to zeros.
    """
    input_t = output_t = total_t = 0
    try:
        usage = getattr(resp, "usage", None) or {}
        # Some SDKs use attributes, others dict-like
        input_t = getattr(usage, "input_tokens", None) or usage.get("input_tokens", 0)
        output_t = getattr(usage, "output_tokens", None) or usage.get("output_tokens", 0)
        total_t = getattr(usage, "total_tokens", None) or usage.get("total_tokens", 0)
        # Fallback compute total if missing
        if not total_t:
            total_t = int(input_t) + int(output_t)
        return {"input": int(input_t or 0), "output": int(output_t or 0), "total": int(total_t or 0)}
    except Exception:
        return {"input": 0, "output": 0, "total": 0}


async def _request_with_retries(coro_factory):
    """
    Retry wrapper:
      - Up to config.RETRY_MAX times
      - Waits at least config.RETRY_DELAY_SEC between tries
      - If a 429/rate-limit suggests a wait (Retry-After header or 'try again in Xs'),
        sleep for max(RETRY_DELAY_SEC, suggested).
      - Records telemetry for Stats footer.
    """
    global _RETRY_COUNT, _RETRY_EVENTS, _RETRY_DELAYS

    last_err = None
    any_retry_this_call = False

    for attempt in range(1, config.RETRY_MAX + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e

            # Base delay from config
            delay = float(config.RETRY_DELAY_SEC)

            # Respect Retry-After header if available
            try:
                resp = getattr(e, "response", None)
                if resp is not None:
                    ra = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
                    if ra:
                        try:
                            delay = max(delay, float(ra))
                        except Exception:
                            pass
            except Exception:
                pass

            # Parse "... Please try again in 29.786s."
            try:
                msg = str(e)
                m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
                if m:
                    suggested = float(m.group(1))
                    delay = max(delay, math.ceil(suggested))
            except Exception:
                pass

            if attempt < config.RETRY_MAX:
                # Telemetry
                if not any_retry_this_call:
                    _RETRY_EVENTS += 1
                    any_retry_this_call = True
                _RETRY_COUNT += 1
                _RETRY_DELAYS.append(delay)

                await asyncio.sleep(delay)
            else:
                raise last_err


async def call_worker(client: AsyncOpenAI, history: List[Dict[str, str]]) -> Tuple[str, Dict[str, int]]:
    async def _do():
        return await client.responses.create(
            model=config.CURRENT_MODEL,
            instructions=config.WORKER_INSTRUCTION,
            input=history,
            reasoning=config.reasoning_dict(),
            text=config.text_dict(),
        )
    resp = await _request_with_retries(_do)
    return _extract_output_text(resp), _extract_usage(resp)


async def call_synth(client: AsyncOpenAI, history: List[Dict[str, str]], drafts: Dict[str, str]) -> Tuple[str, Dict[str, int]]:
    stitched = "\n\n".join(f"### {name}\n{text.strip()}" for name, text in drafts.items())
    synth_input = history + [{"role": "assistant", "content": "WORKER DRAFTS:\n" + stitched}]
    async def _do():
        return await client.responses.create(
            model=config.CURRENT_MODEL,
            instructions=config.SYNTH_INSTRUCTION,
            input=synth_input,
            reasoning=config.reasoning_dict(),
            text=config.text_dict(),
        )
    resp = await _request_with_retries(_do)
    return _extract_output_text(resp), _extract_usage(resp)
