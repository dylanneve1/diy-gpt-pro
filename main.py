# File: main.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from typing import List, Dict

from multiworker.client import create_client_no_timeout
from multiworker.settings_menu import settings_menu
from multiworker.sessions import list_sessions, save_session, load_session, slug
from multiworker.orchestrator import run_turn
from multiworker.ui import console
from multiworker import config

def main():
    client = create_client_no_timeout()
    history: List[Dict[str, str]] = []

    console.print("[bold]Multi-Worker Orchestrator[/bold] — commands: /list, /save <n>, /load <n>, /clear, /settings, /exit")

    while True:
        user_in = input("\nYou: ").strip()
        if not user_in:
            continue

        if user_in.startswith("/exit"):
            break

        if user_in.startswith("/settings"):
            settings_menu()
            continue

        if user_in.startswith("/clear"):
            history = []
            # reset running token totals
            config.RUNNING_TOKENS["input"] = 0
            config.RUNNING_TOKENS["output"] = 0
            config.RUNNING_TOKENS["total"] = 0
            console.print("[yellow]Context cleared and token counters reset.[/yellow]")
            continue

        if user_in.startswith("/list"):
            items = list_sessions()
            if items:
                console.print("[bold cyan]Saved sessions:[/bold cyan] " + ", ".join(items))
            else:
                console.print("[dim]No saved sessions.[/dim]")
            continue

        if user_in.startswith("/save"):
            parts = user_in.split(maxsplit=1)
            if len(parts) < 2:
                console.print("[red]Usage: /save <name>[/red]")
                continue
            path = save_session(parts[1], history, config.RUNNING_TOKENS)
            console.print(f"[green]Saved[/green] → {path}")
            continue

        if user_in.startswith("/load"):
            parts = user_in.split(maxsplit=1)
            if len(parts) < 2:
                console.print("[red]Usage: /load <name>[/red]")
                continue
            loaded = load_session(parts[1])
            if loaded is None:
                console.print("[red]Not found.[/red]")
                continue
            msgs, tokens = loaded
            history = msgs
            # restore running token totals from session file
            config.RUNNING_TOKENS["input"] = tokens.get("input", 0)
            config.RUNNING_TOKENS["output"] = tokens.get("output", 0)
            config.RUNNING_TOKENS["total"] = tokens.get("total", 0)
            console.print(f"[green]Loaded[/green] session '{slug(parts[1])}' "
                          f"with {len(history)} messages. "
                          f"Tokens so far: in={config.RUNNING_TOKENS['input']} "
                          f"out={config.RUNNING_TOKENS['output']} "
                          f"total={config.RUNNING_TOKENS['total']}.")
            continue

        history.append({"role": "user", "content": user_in})
        final_answer = asyncio.run(run_turn(client, history))
        print(final_answer)
        history.append({"role": "assistant", "content": final_answer})

    console.print("[dim]Bye.[/dim]")

if __name__ == "__main__":
    main()
