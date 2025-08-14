# File: multiworker/openai_calls.py
import asyncio
import re
import math
from typing import Dict, List
from openai import AsyncOpenAI

from . import config

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

async def _request_with_retries(coro_factory):
    """
    Retry wrapper:
      - Up to config.RETRY_MAX times
      - Waits at least config.RETRY_DELAY_SEC between tries
      - If a 429 / rate-limit provides a suggested wait (Retry-After header or "try again in Xs"),
        we sleep for max(RETRY_DELAY_SEC, suggested_wait).
    """
    last_err = None
    for attempt in range(1, config.RETRY_MAX + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e

            # Base delay from config
            delay = float(config.RETRY_DELAY_SEC)

            # Try to honor server-provided wait windows when present
            # 1) Retry-After header (if SDK exposes response)
            try:
                resp = getattr(e, "response", None)
                if resp is not None:
                    # httpx.Response-like
                    ra = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
                    if ra:
                        try:
                            suggested = float(ra)
                            delay = max(delay, suggested)
                        except Exception:
                            pass
            except Exception:
                pass

            # 2) Parse message text: "... Please try again in 29.786s."
            try:
                msg = str(e)
                m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
                if m:
                    suggested = float(m.group(1))
                    delay = max(delay, math.ceil(suggested))
            except Exception:
                pass

            if attempt < config.RETRY_MAX:
                await asyncio.sleep(delay)
            else:
                raise last_err

async def call_worker(client: AsyncOpenAI, history: List[Dict[str, str]]) -> str:
    async def _do():
        return await client.responses.create(
            model=config.CURRENT_MODEL,
            instructions=config.WORKER_INSTRUCTION,
            input=history,
            reasoning=config.reasoning_dict(),
            text=config.text_dict(),
        )
    resp = await _request_with_retries(_do)
    return _extract_output_text(resp)

async def call_synth(client: AsyncOpenAI, history: List[Dict[str, str]], drafts: Dict[str, str]) -> str:
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
    return _extract_output_text(resp)
