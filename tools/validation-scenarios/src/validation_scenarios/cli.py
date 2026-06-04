"""CLI entry point for Mímir validation scenarios."""

import asyncio
from pathlib import Path
from uuid import UUID

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from validation_scenarios.analyzer import (
    get_available_perspectives,
    ingest_file,
)
from validation_scenarios.llm import get_model_info
from validation_scenarios.mimir_client import MimirClient

# Load environment variables from local .env
load_dotenv()

app = typer.Typer(
    name="mimir-validate",
    help=(
        "Legacy demo scaffold for Mimir validation scenarios; "
        "pending v5.5 contract modernization."
    ),
    no_args_is_help=True,
)
console = Console()


def run_async(coro):
    """Run async function in sync context."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# INGEST COMMAND
# =============================================================================


@app.command()
def ingest(
    file: Path = typer.Argument(..., help="File to ingest", exists=True, readable=True),
    perspectives: str = typer.Option(
        None,
        "--perspectives", "-p",
        help="Comma-separated perspectives to analyze: summary,findings,questions,analysis,insights. "
        "Use 'all' for all perspectives. Omit to skip analysis.",
    ),
):
    """Ingest a file into Mímir and optionally analyze it from multiple perspectives."""
    
    # Parse perspectives
    perspective_list = None
    if perspectives:
        if perspectives.lower() == "all":
            perspective_list = get_available_perspectives()
        else:
            perspective_list = [p.strip() for p in perspectives.split(",") if p.strip()]
    
    # Read file content
    content = file.read_text()
    
    console.print(f"\n[bold]Ingesting:[/bold] {file.name}")
    console.print(f"[dim]Size: {len(content):,} characters[/dim]")
    
    if perspective_list:
        model_info = get_model_info()
        console.print(f"[dim]LLM: {model_info['provider']}:{model_info['model']}[/dim]")
        console.print(f"[dim]Perspectives: {', '.join(perspective_list)}[/dim]\n")
    
    async def do_ingest():
        async with MimirClient() as client:
            # Check API health
            if not await client.health_check():
                console.print("[red]Error: Mímir API is not available[/red]")
                raise typer.Exit(1)
            
            return await ingest_file(
                client=client,
                file_path=str(file),
                content=content,
                analyze_perspectives=perspective_list,
            )
    
    with console.status("[bold green]Processing..."):
        result = run_async(do_ingest())
    
    # Display results
    doc = result["document"]
    console.print(Panel(
        f"[green]✓[/green] Document created\n"
        f"[bold]ID:[/bold] {doc['id']}\n"
        f"[bold]Type:[/bold] {doc['artifact_type']}\n"
        f"[bold]Title:[/bold] {doc['title']}",
        title="Document",
    ))
    
    if result["analyses"]:
        table = Table(title="Analyses Created")
        table.add_column("Perspective", style="cyan")
        table.add_column("Artifact ID", style="dim")
        table.add_column("Type", style="green")
        
        for analysis in result["analyses"]:
            table.add_row(
                analysis["perspective"],
                analysis["artifact"]["id"],
                analysis["artifact"]["artifact_type"],
            )
        
        console.print(table)
    
    console.print(f"\n[dim]Use 'mimir-validate context {doc['id']}' to retrieve with context[/dim]")


# =============================================================================
# CONTEXT COMMAND
# =============================================================================


@app.command()
def context(
    artifact_id: str = typer.Argument(..., help="Artifact UUID to retrieve with context"),
    policy: str = typer.Option(
        "derived_lineage",
        "--policy", "-p",
        help="Context policy: direct_relations, derived_lineage, evidence_chain, full_graph",
    ),
    depth: int = typer.Option(2, "--depth", "-d", help="Traversal depth"),
):
    """Retrieve an artifact with all contextually relevant artifacts."""
    
    try:
        uuid = UUID(artifact_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {artifact_id}[/red]")
        raise typer.Exit(1)
    
    async def do_context():
        async with MimirClient() as client:
            return await client.get_context(uuid, policy=policy, depth=depth)
    
    with console.status("[bold green]Retrieving context..."):
        result = run_async(do_context())
    
    if not result:
        console.print(f"[red]Artifact not found: {artifact_id}[/red]")
        raise typer.Exit(1)
    
    # Display primary artifact
    artifact = result["artifact"]
    console.print(Panel(
        f"[bold]ID:[/bold] {artifact['id']}\n"
        f"[bold]Type:[/bold] {artifact['artifact_type']}\n"
        f"[bold]Title:[/bold] {artifact.get('title', 'N/A')}\n"
        f"[bold]Created:[/bold] {artifact['created_at']}",
        title="Primary Artifact",
    ))
    
    # Display content preview
    content = artifact.get("content", "")
    if content:
        preview = content[:500] + "..." if len(content) > 500 else content
        console.print(Panel(preview, title="Content Preview", border_style="dim"))
    
    # Display context
    context_items = result.get("context", [])
    if context_items:
        table = Table(title=f"Context ({len(context_items)} artifacts)")
        table.add_column("Distance", style="dim", width=8)
        table.add_column("Type", style="cyan")
        table.add_column("Title")
        table.add_column("Reason", style="dim")
        
        for ctx in context_items:
            ctx_artifact = ctx["artifact"]
            table.add_row(
                str(ctx["distance"]),
                ctx_artifact["artifact_type"],
                ctx_artifact.get("title", "N/A")[:40],
                ctx["inclusion_reason"][:30],
            )
        
        console.print(table)
    else:
        console.print("[dim]No context artifacts found[/dim]")
    
    # Display metadata
    meta = result.get("metadata", {})
    console.print(f"\n[dim]Policy: {result.get('policy', policy)} | "
                  f"Depth: {meta.get('depth_used', depth)} | "
                  f"Context items: {meta.get('artifact_count', 0)}[/dim]")


# =============================================================================
# SEARCH COMMAND
# =============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    artifact_types: str = typer.Option(
        None, "--types", "-t",
        help="Filter by artifact types (comma-separated)",
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum results"),
):
    """Search for artifacts using full-text search."""
    
    types_list = None
    if artifact_types:
        types_list = [t.strip() for t in artifact_types.split(",") if t.strip()]
    
    async def do_search():
        async with MimirClient() as client:
            return await client.fulltext_search(
                query=query,
                artifact_types=types_list,
                limit=limit,
            )
    
    with console.status("[bold green]Searching..."):
        result = run_async(do_search())
    
    results = result.get("results", [])
    
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    
    table = Table(title=f"Search Results ({result.get('total', len(results))} total)")
    table.add_column("Rank", style="dim", width=6)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Type", style="green")
    table.add_column("Title")
    table.add_column("ID", style="dim")
    
    for r in results:
        artifact = r["artifact"]
        table.add_row(
            str(r.get("rank", "-")),
            f"{r.get('score', 0):.3f}",
            artifact["artifact_type"],
            (artifact.get("title") or "")[:40],
            artifact["id"][:8] + "...",
        )
    
    console.print(table)


# =============================================================================
# STATUS COMMAND
# =============================================================================


@app.command()
def status():
    """Check Mímir API health and show configuration."""
    
    import os
    
    # Configuration
    console.print("\n[bold]Configuration[/bold]")
    config_table = Table(show_header=False, box=None)
    config_table.add_column("Key", style="cyan")
    config_table.add_column("Value")
    
    config_table.add_row("MIMIR_BASE_URL", os.getenv("MIMIR_BASE_URL", "http://localhost:38000"))
    config_table.add_row("MIMIR_TENANT_ID", os.getenv("MIMIR_TENANT_ID", "1"))
    
    model_info = get_model_info()
    config_table.add_row("LLM_MODEL", f"{model_info['provider']}:{model_info['model']}")
    
    console.print(config_table)
    
    # Health check
    async def check_health():
        async with MimirClient() as client:
            return await client.health_check()
    
    console.print("\n[bold]API Status[/bold]")
    healthy = run_async(check_health())
    
    if healthy:
        console.print("[green]✓ Mímir API is available[/green]")
    else:
        console.print("[red]✗ Mímir API is not available[/red]")


# =============================================================================
# PERSPECTIVES COMMAND
# =============================================================================


@app.command()
def perspectives():
    """List available analysis perspectives."""
    
    from validation_scenarios.analyzer import PERSPECTIVES
    
    table = Table(title="Available Perspectives")
    table.add_column("Name", style="cyan")
    table.add_column("Artifact Type", style="green")
    table.add_column("Description")
    
    descriptions = {
        "summary": "Concise overview of main points",
        "findings": "Key facts, statistics, and claims",
        "questions": "Questions the content prompts",
        "analysis": "Strengths, weaknesses, assumptions",
        "insights": "Actionable takeaways",
    }
    
    for name, (artifact_type, _) in PERSPECTIVES.items():
        table.add_row(name, artifact_type, descriptions.get(name, ""))
    
    console.print(table)
    console.print("\n[dim]Use --perspectives name1,name2 or --perspectives all with ingest command[/dim]")


if __name__ == "__main__":
    app()
