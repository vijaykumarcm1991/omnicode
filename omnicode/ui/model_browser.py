"""
Interactive model browser with pagination, searching, and context limit detection.
Handles endpoints with large model catalogs (e.g. OpenRouter, vLLM, Ollama, KodeKloud).
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from ..config import detect_context_limit


def filter_models(models: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Filter models by substring match on id or owner."""
    if not query.strip():
        return models
    q = query.strip().lower()
    return [
        m for m in models
        if q in m.get("id", "").lower() or q in m.get("owned_by", "").lower()
    ]


def build_models_table(
    models: List[Dict[str, Any]],
    page: int = 1,
    page_size: int = 15,
    query: str = "",
    title_prefix: str = "Available Models",
) -> Tuple[Table, int, int]:
    """
    Build a Rich table for a specific page of models.
    Returns (Table, total_pages, total_filtered_count).
    """
    filtered = filter_models(models, query)
    total_count = len(filtered)
    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_count)

    subtitle = f"Page {page} of {total_pages} (Total: {total_count} models)"
    if query:
        subtitle += f" [Filtered by: '{query}']"

    table = Table(
        title=f"[bold cyan]{title_prefix}[/bold cyan]\n[dim]{subtitle}[/dim]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=5)
    table.add_column("Model ID", style="bold green")
    table.add_column("Context Window", style="magenta")
    table.add_column("Owner", style="dim")

    for i in range(start_idx, end_idx):
        m = filtered[i]
        ctx_len = detect_context_limit(m["id"], m.get("raw"))
        table.add_row(str(i + 1), m["id"], f"{ctx_len:,} tokens", m.get("owned_by", "unknown"))

    return table, total_pages, total_count


def browse_models_interactive(
    discovered_models: List[Dict[str, Any]],
    console: Console,
    default_model: str = "",
    page_size: int = 15,
) -> Tuple[str, int]:
    """
    Interactive paginated model browser with search, scroll, and selection.
    Returns (selected_model_id, context_window).
    """
    if not discovered_models:
        selected = Prompt.ask(
            "[bold white]Enter model name[/bold white]",
            default=default_model or "default",
            console=console,
        ).strip()
        ctx = detect_context_limit(selected)
        return selected, ctx

    current_page = 1
    current_query = ""

    while True:
        filtered = filter_models(discovered_models, current_query)
        total_count = len(filtered)
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        current_page = max(1, min(current_page, total_pages))

        table, total_pages, total_count = build_models_table(
            discovered_models,
            page=current_page,
            page_size=page_size,
            query=current_query,
            title_prefix="Discovered Models from Endpoint",
        )
        console.print(table)

        # Navigational instructions
        nav_hints = []
        if total_pages > 1:
            nav_hints.append("[bold cyan]n[/bold cyan]: Next Page")
            nav_hints.append("[bold cyan]p[/bold cyan]: Prev Page")
        nav_hints.append("[bold cyan]s <text>[/bold cyan]: Search/Filter")
        if current_query:
            nav_hints.append("[bold cyan]c[/bold cyan]: Clear Search")
        nav_hints.append("[bold cyan]1..N[/bold cyan]: Select Number")
        nav_hints.append("[bold cyan]<model-id>[/bold cyan]: Type Name")

        console.print(f"[dim]Actions: {' | '.join(nav_hints)}[/dim]")

        prompt_default = "1" if total_count > 0 else (default_model or "")
        choice = Prompt.ask(
            "\n[bold white]Select model # or navigation command[/bold white]",
            default=prompt_default,
            console=console,
        ).strip()

        if not choice:
            choice = prompt_default

        choice_lower = choice.lower()

        # Navigation commands
        if choice_lower in ["n", "next"] and total_pages > 1:
            if current_page < total_pages:
                current_page += 1
            else:
                console.print("[dim yellow]Already on the last page. Wrapping to page 1.[/dim yellow]")
                current_page = 1
            continue

        elif choice_lower in ["p", "prev", "previous"] and total_pages > 1:
            if current_page > 1:
                current_page -= 1
            else:
                console.print(f"[dim yellow]Already on the first page. Wrapping to page {total_pages}.[/dim yellow]")
                current_page = total_pages
            continue

        elif choice_lower in ["c", "clear"]:
            current_query = ""
            current_page = 1
            console.print("[dim]Cleared filter.[/dim]")
            continue

        elif choice_lower.startswith("s ") or choice_lower.startswith("f ") or choice_lower.startswith("search ") or choice_lower.startswith("filter "):
            parts = choice.split(maxsplit=1)
            query_arg = parts[1].strip() if len(parts) > 1 else ""
            current_query = query_arg
            current_page = 1
            console.print(f"[dim]Searching for: '{current_query}'[/dim]")
            continue

        # Number selection
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(filtered):
                selected_item = filtered[idx - 1]
                model_id = selected_item["id"]
                ctx = detect_context_limit(model_id, selected_item.get("raw"))
                return model_id, ctx
            else:
                console.print(f"[bold red]Invalid number {idx}. Choose between 1 and {len(filtered)}.[/bold red]")
                continue

        # Direct model name input
        selected_model = choice
        raw_meta = next(
            (m.get("raw") for m in discovered_models if m["id"].lower() == selected_model.lower()),
            None,
        )
        ctx = detect_context_limit(selected_model, raw_meta)
        return selected_model, ctx
