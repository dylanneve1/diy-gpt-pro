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

def main():
    client = create_client_no_timeout()
    history: List[Dict[str, str]] = []

    console.print("[bold]Multi-Worker Orchestrator[/bold] — commands: /list, /save <n>, /load <n>, /settings, /exit")

    while True:
        user_in = input("\nYou: ").strip()
        if not user_in:
            continue

        if user_in.startswith("/exit"):
            break

        if user_in.startswith("/settings"):
            settings_menu()
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
            path = save_session(parts[1], history)
            console.print(f"[green]Saved[/green] → {path}")
            continue

        if user_in.startswith("/load"):
            parts = user_in.split(maxsplit=1)
            if len(parts) < 2:
                console.print("[red]Usage: /load <name>[/red]")
                continue
            msgs = load_session(parts[1])
            if msgs is None:
                console.print("[red]Not found.[/red]")
                continue
            history = msgs
            console.print(f"[green]Loaded[/green] session '{slug(parts[1])}' with {len(history)} messages.")
            continue

        history.append({"role": "user", "content": user_in})
        final_answer = asyncio.run(run_turn(client, history))
        print(final_answer)
        history.append({"role": "assistant", "content": final_answer})

    console.print("[dim]Bye.[/dim]")

if __name__ == "__main__":
    main()
