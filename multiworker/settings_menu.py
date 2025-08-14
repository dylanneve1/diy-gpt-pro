# File: multiworker/settings_menu.py
from .ui import console
from . import config

def settings_menu() -> None:
    levels = ["minimal", "low", "medium", "high"]
    while True:
        console.print("\n[bold cyan]Settings[/bold cyan]")
        log_status = "[green]ON[/green]" if config.LOG_ALL_TO_FILE else "[red]OFF[/red]"
        console.print(f"  1) Log all model responses to TXT file: {log_status}")
        console.print(f"  2) Reasoning level: [bold]{config.REASONING_LEVEL}[/bold] (choices: {', '.join(levels)})")
        console.print(f"  3) Model: [bold]{config.CURRENT_MODEL}[/bold] (choices: {', '.join(config.MODEL_CHOICES)})")
        console.print(f"  4) Workers: [bold]{config.N_WORKERS}[/bold] (restart recommended after change)")
        console.print(f"  5) Retry policy: max={config.RETRY_MAX}, delay={config.RETRY_DELAY_SEC}s")
        console.print("  t) Toggle logging   r) Set reasoning   m) Set model   q) Back\n")
        choice = input("> ").strip().lower()
        if choice in ("1", "t", "toggle"):
            config.LOG_ALL_TO_FILE = not config.LOG_ALL_TO_FILE
        elif choice in ("2", "r", "reasoning"):
            new_level = input("Enter reasoning level (minimal|low|medium|high): ").strip().lower()
            if new_level in levels:
                config.REASONING_LEVEL = new_level
                console.print(f"[green]Reasoning set to {config.REASONING_LEVEL}[/green]")
            else:
                console.print("[red]Invalid level.[/red]")
        elif choice in ("3", "m", "model"):
            new_model = input(f"Enter model ({', '.join(config.MODEL_CHOICES)}): ").strip()
            if new_model in config.MODEL_CHOICES:
                config.CURRENT_MODEL = new_model
                console.print(f"[green]Model set to {config.CURRENT_MODEL}[/green]")
            else:
                console.print("[red]Invalid model.[/red]")
        elif choice in ("q", "b", "back", ""):
            break
