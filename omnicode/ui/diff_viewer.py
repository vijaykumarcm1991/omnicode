"""
Diff viewer utility using Rich for syntax-highlighted code diffs.
"""

import difflib
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


def render_diff(
    old_text: str,
    new_text: str,
    filename: str = "file",
    console: Console = None,
) -> None:
    """Render a colored side-by-side or unified diff in terminal."""
    con = console or Console()
    diff = list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=3,
        )
    )

    if not diff:
        con.print(f"[dim]No changes in {filename}[/dim]")
        return

    diff_str = "".join(diff)
    syntax = Syntax(diff_str, "diff", theme="monokai", line_numbers=False)
    con.print(
        Panel(
            syntax,
            title=f"[bold yellow]Diff: {filename}[/bold yellow]",
            border_style="yellow",
        )
    )
