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
        console.print(f"  4) Workers: [bold]{config.N_WORKERS}[/bold] (saved; restart to fully apply)")
        console.print(f"  5) Retry policy: max={config.RETRY_MAX}, delay={config.RETRY_DELAY_SEC}s")
        console.print("  t) Toggle logging   r) Set reasoning   m) Set model   n) Set workers   q) Back\n")

        choice = input("> ").strip().lower()
        if choice in ("1", "t", "toggle"):
            config.LOG_ALL_TO_FILE = not config.LOG_ALL_TO_FILE
            config.save_settings()
            console.print(f"[green]Logging set to {'ON' if config.LOG_ALL_TO_FILE else 'OFF'} (saved)[/green]")

        elif choice in ("2", "r", "reasoning"):
            new_level = input("Enter reasoning level (minimal|low|medium|high): ").strip().lower()
            if new_level in levels:
                config.REASONING_LEVEL = new_level
                config.save_settings()
                console.print(f"[green]Reasoning set to {config.REASONING_LEVEL} (saved)[/green]")
            else:
                console.print("[red]Invalid level.[/red]")

        elif choice in ("3", "m", "model"):
            new_model = input(f"Enter model ({', '.join(config.MODEL_CHOICES)}): ").strip()
            if new_model in config.MODEL_CHOICES:
                config.CURRENT_MODEL = new_model
                config.save_settings()
                console.print(f"[green]Model set to {config.CURRENT_MODEL} (saved)[/green]")
            else:
                console.print("[red]Invalid model.[/red]")

        elif choice in ("n", "4", "workers"):
            try:
                new_n = int(input("Enter number of workers (1-8): ").strip())
                if 1 <= new_n <= 8:
                    config.N_WORKERS = new_n
                    # Regenerate names and persist immediately
                    config.WORKER_NAMES[:] = [f"Worker-{i+1}" for i in range(config.N_WORKERS)]
                    config.save_settings()
                    console.print(f"[green]Workers set to {config.N_WORKERS} (saved). Restart recommended.[/green]")
                else:
                    console.print("[red]Value out of range (1-8).[/red]")
            except Exception:
                console.print("[red]Invalid number.[/red]")

        elif choice in ("q", "b", "back", ""):
            break
