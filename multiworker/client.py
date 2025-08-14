# File: multiworker/client.py
import os
from openai import AsyncOpenAI

def create_client_no_timeout() -> AsyncOpenAI:
    """
    Create an AsyncOpenAI client with no HTTP timeout if supported by the SDK,
    otherwise fall back to an httpx client with timeout disabled.
    """
    try:
        return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"), timeout=None)
    except TypeError:
        try:
            import httpx
            http_client = httpx.AsyncClient(timeout=None)
            return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"), http_client=http_client)
        except Exception:
            return AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
