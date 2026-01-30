#!/usr/bin/env python3
"""
ChatGPT Export Intake Script

Process ChatGPT export files (conversations.json) for:
- Listing conversations
- Exporting to markdown
- Ingesting to Mímir API

Usage:
    python scripts/ingest_chatgpt.py list chatgpt_export/conversations.json
    python scripts/ingest_chatgpt.py export chatgpt_export/conversations.json --output-dir ./md
    python scripts/ingest_chatgpt.py ingest chatgpt_export/conversations.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# ============================================================================
# Configuration
# ============================================================================

API_BASE_URL = "http://localhost:38000/api/v1"
DEFAULT_TENANT_ID = 1
DEFAULT_OUTPUT_DIR = Path("./chatgpt_md")

# ============================================================================
# Data Types
# ============================================================================


class ConversationSummary:
    """Lightweight summary of a conversation for listing."""

    __slots__ = ("id", "title", "create_time", "update_time", "message_count", "is_archived")

    def __init__(
        self,
        id: str,
        title: str,
        create_time: datetime | None,
        update_time: datetime | None,
        message_count: int,
        is_archived: bool,
    ):
        self.id = id
        self.title = title
        self.create_time = create_time
        self.update_time = update_time
        self.message_count = message_count
        self.is_archived = is_archived

    @property
    def id_short(self) -> str:
        """First 8 characters of ID for display."""
        return self.id[:8] if self.id else ""

    @property
    def date_str(self) -> str:
        """Formatted date for display."""
        if self.create_time:
            return self.create_time.strftime("%Y-%m-%d")
        return "unknown"


class Message:
    """Extracted message from conversation tree."""

    __slots__ = ("id", "role", "content", "create_time", "model")

    def __init__(
        self,
        id: str,
        role: str,
        content: str,
        create_time: datetime | None,
        model: str | None,
    ):
        self.id = id
        self.role = role
        self.content = content
        self.create_time = create_time
        self.model = model


# ============================================================================
# Parsing Functions
# ============================================================================


def parse_timestamp(ts: float | None) -> datetime | None:
    """Convert Unix timestamp to datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (OSError, ValueError):
        return None


def extract_content(message: dict | None) -> str:
    """Extract text content from a message object."""
    if not message:
        return ""
    content = message.get("content")
    if not content:
        return ""
    if content.get("content_type") == "text":
        parts = content.get("parts", [])
        return "\n".join(str(p) for p in parts if p)
    content_type = content.get("content_type", "unknown")
    return f"[{content_type} content]"


def count_visible_messages(mapping: dict) -> int:
    """Count non-system messages with content."""
    count = 0
    for node in mapping.values():
        message = node.get("message")
        if not message:
            continue
        author = message.get("author", {})
        role = author.get("role", "")
        if role == "system":
            continue
        weight = message.get("weight", 1.0)
        if weight <= 0:
            continue
        content = extract_content(message)
        if content.strip():
            count += 1
    return count


def extract_conversation_summary(conv: dict) -> ConversationSummary:
    """Extract summary info from a conversation object."""
    return ConversationSummary(
        id=conv.get("id", ""),
        title=conv.get("title", "Untitled"),
        create_time=parse_timestamp(conv.get("create_time")),
        update_time=parse_timestamp(conv.get("update_time")),
        message_count=count_visible_messages(conv.get("mapping", {})),
        is_archived=conv.get("is_archived", False),
    )


def traverse_messages(conv: dict) -> list[Message]:
    """
    Traverse the message tree from current_node to root, return chronological order.
    Filters out system messages and empty content.
    """
    mapping = conv.get("mapping", {})
    current_node_id = conv.get("current_node")

    if not current_node_id or current_node_id not in mapping:
        return []

    # Walk from current_node to root
    path = []
    node_id = current_node_id
    visited = set()

    while node_id and node_id not in visited:
        visited.add(node_id)
        node = mapping.get(node_id)
        if not node:
            break

        message = node.get("message")
        if message:
            author = message.get("author", {})
            role = author.get("role", "")
            weight = message.get("weight", 1.0)

            # Skip system messages and hidden messages
            if role != "system" and weight > 0:
                content = extract_content(message)
                if content.strip():
                    path.append(
                        Message(
                            id=message.get("id", ""),
                            role=role,
                            content=content,
                            create_time=parse_timestamp(message.get("create_time")),
                            model=message.get("metadata", {}).get("model_slug"),
                        )
                    )

        node_id = node.get("parent")

    # Reverse to get chronological order
    path.reverse()
    return path


def load_conversations(file_path: Path) -> list[dict]:
    """Load and parse conversations.json file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Expected JSON array of conversations")

    return data


def filter_conversations(
    summaries: list[ConversationSummary],
    filter_text: str | None = None,
    include_archived: bool = False,
) -> list[ConversationSummary]:
    """Filter conversation summaries by criteria."""
    result = summaries

    if not include_archived:
        result = [s for s in result if not s.is_archived]

    if filter_text:
        pattern = filter_text.lower()
        result = [s for s in result if pattern in s.title.lower()]

    return result


# ============================================================================
# Markdown Export
# ============================================================================


def sanitize_filename(title: str, max_length: int = 50) -> str:
    """Convert title to safe filename component."""
    # Lowercase and replace spaces/special chars with hyphens
    safe = re.sub(r"[^\w\s-]", "", title.lower())
    safe = re.sub(r"[-\s]+", "-", safe).strip("-")
    return safe[:max_length]


def generate_markdown(conv: dict) -> str:
    """Generate markdown content for a conversation."""
    summary = extract_conversation_summary(conv)
    messages = traverse_messages(conv)

    lines = [
        f"# {summary.title}",
        "",
        f"**ID:** {summary.id}  ",
        f"**Created:** {summary.create_time.strftime('%Y-%m-%d %H:%M:%S UTC') if summary.create_time else 'unknown'}",
        "",
    ]

    for msg in messages:
        lines.append("---")
        lines.append("")
        lines.append(f"## {msg.role.capitalize()}")
        if msg.create_time:
            lines.append(f"*{msg.create_time.strftime('%H:%M:%S')}*")
        lines.append("")
        lines.append(msg.content)
        lines.append("")

    return "\n".join(lines)


def export_conversation(conv: dict, output_dir: Path, overwrite: bool = False) -> Path | None:
    """Export a single conversation to markdown file."""
    summary = extract_conversation_summary(conv)

    # Generate filename
    date_str = summary.create_time.strftime("%Y-%m-%d") if summary.create_time else "unknown"
    safe_title = sanitize_filename(summary.title)
    filename = f"{date_str}_{safe_title}_{summary.id_short}.md"
    file_path = output_dir / filename

    if file_path.exists() and not overwrite:
        return None

    content = generate_markdown(conv)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


# ============================================================================
# API Client
# ============================================================================


def ensure_tenant(client: httpx.Client, api_url: str, tenant_id: int) -> dict:
    """Ensure tenant exists, create if not."""
    response = client.get(f"{api_url}/tenants/{tenant_id}")
    if response.status_code == 200:
        return response.json()

    if response.status_code == 404:
        response = client.post(
            f"{api_url}/tenants",
            json={"name": "ChatGPT Import", "metadata": {"created_by": "ingest_chatgpt.py"}},
        )
        response.raise_for_status()
        return response.json()

    response.raise_for_status()
    return {}


def create_artifact(
    client: httpx.Client,
    api_url: str,
    tenant_id: int,
    artifact_type: str,
    title: str,
    content: str | None = None,
    external_id: str | None = None,
    parent_artifact_id: int | None = None,
    source: str = "chatgpt",
    source_system: str = "chatgpt_export",
    metadata: dict | None = None,
    position_metadata: dict | None = None,
) -> dict:
    """Create an artifact via API."""
    payload = {
        "artifact_type": artifact_type,
        "title": title,
        "source": source,
        "source_system": source_system,
    }

    if content:
        payload["content"] = content
    if external_id:
        payload["external_id"] = external_id
    if parent_artifact_id:
        payload["parent_artifact_id"] = parent_artifact_id
    if metadata:
        payload["metadata"] = metadata
    if position_metadata:
        payload["position_metadata"] = position_metadata

    response = client.post(
        f"{api_url}/artifacts",
        json=payload,
        headers={"X-Tenant-ID": str(tenant_id)},
    )
    response.raise_for_status()
    return response.json()


def create_relation(
    client: httpx.Client,
    api_url: str,
    tenant_id: int,
    relation_type: str,
    source_type: str,
    source_id: int,
    target_type: str,
    target_id: int,
) -> dict:
    """Create a relation via API."""
    payload = {
        "relation_type": relation_type,
        "source_type": source_type,
        "source_id": source_id,
        "target_type": target_type,
        "target_id": target_id,
    }

    response = client.post(
        f"{api_url}/relations",
        json=payload,
        headers={"X-Tenant-ID": str(tenant_id)},
    )
    response.raise_for_status()
    return response.json()


def ingest_conversation(
    client: httpx.Client,
    api_url: str,
    tenant_id: int,
    conv: dict,
) -> tuple[int, int, int]:
    """
    Ingest a single conversation with all messages.
    Returns (conversation_artifacts, message_artifacts, relations).
    """
    summary = extract_conversation_summary(conv)
    messages = traverse_messages(conv)

    # Create conversation artifact
    conv_artifact = create_artifact(
        client=client,
        api_url=api_url,
        tenant_id=tenant_id,
        artifact_type="conversation",
        title=summary.title,
        external_id=summary.id,
        metadata={
            "create_time": summary.create_time.isoformat() if summary.create_time else None,
            "update_time": summary.update_time.isoformat() if summary.update_time else None,
            "is_archived": summary.is_archived,
            "message_count": summary.message_count,
        },
    )
    conv_id = conv_artifact["id"]

    # Create message artifacts
    message_artifacts = []
    for seq, msg in enumerate(messages, start=1):
        title_preview = f"{msg.role}: {msg.content[:50]}..." if len(msg.content) > 50 else f"{msg.role}: {msg.content}"
        msg_artifact = create_artifact(
            client=client,
            api_url=api_url,
            tenant_id=tenant_id,
            artifact_type="message",
            title=title_preview,
            content=msg.content,
            external_id=msg.id,
            parent_artifact_id=conv_id,
            metadata={
                "author_role": msg.role,
                "create_time": msg.create_time.isoformat() if msg.create_time else None,
                "model": msg.model,
            },
            position_metadata={"sequence": seq},
        )
        message_artifacts.append(msg_artifact)

    # Create relations
    relations_created = 0

    # Conversation contains each message
    for msg_artifact in message_artifacts:
        create_relation(
            client=client,
            api_url=api_url,
            tenant_id=tenant_id,
            relation_type="contains",
            source_type="artifact",
            source_id=conv_id,
            target_type="artifact",
            target_id=msg_artifact["id"],
        )
        relations_created += 1

    # Message follows previous message
    for i in range(1, len(message_artifacts)):
        create_relation(
            client=client,
            api_url=api_url,
            tenant_id=tenant_id,
            relation_type="follows",
            source_type="artifact",
            source_id=message_artifacts[i]["id"],
            target_type="artifact",
            target_id=message_artifacts[i - 1]["id"],
        )
        relations_created += 1

    return (1, len(message_artifacts), relations_created)


# ============================================================================
# CLI Application
# ============================================================================

app = typer.Typer(
    name="ingest-chatgpt",
    help="Process ChatGPT export files for Mímir",
    no_args_is_help=True,
)
console = Console()


@app.command(name="list")
def list_conversations(
    file: Annotated[Path, typer.Argument(help="Path to conversations.json")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    filter_text: Annotated[str | None, typer.Option("--filter", "-f", help="Filter by title")] = None,
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Limit results")] = None,
    include_archived: Annotated[bool, typer.Option("--archived", help="Include archived")] = False,
):
    """List conversations in a ChatGPT export file."""
    try:
        conversations = load_conversations(file)
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        rprint(f"[red]Error:[/red] Invalid JSON: {e}")
        raise typer.Exit(1)

    # Extract summaries
    summaries = [extract_conversation_summary(c) for c in conversations]

    # Filter
    summaries = filter_conversations(summaries, filter_text, include_archived)

    # Sort by date descending
    summaries.sort(key=lambda s: s.create_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # Limit
    if limit:
        summaries = summaries[:limit]

    # Output
    if json_output:
        output = {
            "total": len(conversations),
            "filtered": len(summaries),
            "conversations": [
                {
                    "id": s.id,
                    "title": s.title,
                    "create_time": s.create_time.isoformat() if s.create_time else None,
                    "update_time": s.update_time.isoformat() if s.update_time else None,
                    "message_count": s.message_count,
                    "is_archived": s.is_archived,
                }
                for s in summaries
            ],
        }
        rprint(json.dumps(output, indent=2))
    else:
        # Rich table output
        archived_count = sum(1 for s in [extract_conversation_summary(c) for c in conversations] if s.is_archived)

        rprint(f"\n[bold]ChatGPT Export:[/bold] {len(conversations)} conversations ({archived_count} archived)\n")

        if not summaries:
            rprint("[yellow]No conversations match the filter.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=4)
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Title", width=50)
        table.add_column("Messages", justify="right", width=8)
        table.add_column("Date", width=12)

        for i, s in enumerate(summaries, start=1):
            table.add_row(
                str(i),
                s.id_short,
                s.title[:50] + "..." if len(s.title) > 50 else s.title,
                str(s.message_count),
                s.date_str,
            )

        console.print(table)


@app.command()
def export(
    file: Annotated[Path, typer.Argument(help="Path to conversations.json")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Output directory")] = DEFAULT_OUTPUT_DIR,
    conv_id: Annotated[str | None, typer.Option("--id", help="Export specific conversation by ID prefix")] = None,
    filter_text: Annotated[str | None, typer.Option("--filter", "-f", help="Filter by title")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing files")] = False,
):
    """Export conversations to markdown files."""
    try:
        conversations = load_conversations(file)
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        rprint(f"[red]Error:[/red] Invalid JSON: {e}")
        raise typer.Exit(1)

    # Filter by ID prefix
    if conv_id:
        conversations = [c for c in conversations if c.get("id", "").startswith(conv_id)]

    # Filter by title
    if filter_text:
        pattern = filter_text.lower()
        conversations = [c for c in conversations if pattern in c.get("title", "").lower()]

    if not conversations:
        rprint("[yellow]No conversations match the criteria.[/yellow]")
        raise typer.Exit(0)

    rprint(f"\n[bold]Exporting {len(conversations)} conversations to {output_dir}[/bold]\n")

    exported = 0
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Exporting...", total=len(conversations))

        for conv in conversations:
            result = export_conversation(conv, output_dir, overwrite)
            if result:
                exported += 1
            else:
                skipped += 1
            progress.advance(task)

    rprint(f"\n[green]✓ Exported {exported} conversations[/green]")
    if skipped:
        rprint(f"[yellow]  Skipped {skipped} (already exist)[/yellow]")


@app.command()
def ingest(
    file: Annotated[Path, typer.Argument(help="Path to conversations.json")],
    api_url: Annotated[str, typer.Option("--api-url", help="Mímir API URL")] = API_BASE_URL,
    tenant_id: Annotated[int, typer.Option("--tenant-id", "-t", help="Tenant ID")] = DEFAULT_TENANT_ID,
    conv_id: Annotated[str | None, typer.Option("--id", help="Ingest specific conversation by ID prefix")] = None,
    filter_text: Annotated[str | None, typer.Option("--filter", "-f", help="Filter by title")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be ingested")] = False,
    embed: Annotated[bool, typer.Option("--embed", help="Create embeddings")] = False,
):
    """Ingest conversations to Mímir API."""
    try:
        conversations = load_conversations(file)
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        rprint(f"[red]Error:[/red] Invalid JSON: {e}")
        raise typer.Exit(1)

    # Filter by ID prefix
    if conv_id:
        conversations = [c for c in conversations if c.get("id", "").startswith(conv_id)]

    # Filter by title
    if filter_text:
        pattern = filter_text.lower()
        conversations = [c for c in conversations if pattern in c.get("title", "").lower()]

    if not conversations:
        rprint("[yellow]No conversations match the criteria.[/yellow]")
        raise typer.Exit(0)

    rprint(f"\n[bold]Ingesting {len(conversations)} conversations to {api_url}[/bold]")
    rprint(f"Tenant: {tenant_id}\n")

    if dry_run:
        rprint("[yellow]DRY RUN - no changes will be made[/yellow]\n")
        for conv in conversations:
            summary = extract_conversation_summary(conv)
            messages = traverse_messages(conv)
            rprint(f"  • [cyan]{summary.id_short}[/cyan] {summary.title} ({len(messages)} messages)")
        rprint(f"\n[yellow]Would create {len(conversations)} conversation artifacts[/yellow]")
        return

    total_convs = 0
    total_msgs = 0
    total_rels = 0
    errors = 0

    with httpx.Client(timeout=30.0) as client:
        # Ensure tenant exists
        try:
            ensure_tenant(client, api_url, tenant_id)
        except httpx.HTTPError as e:
            rprint(f"[red]Error connecting to API:[/red] {e}")
            raise typer.Exit(1)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Ingesting...", total=len(conversations))

            for conv in conversations:
                try:
                    c, m, r = ingest_conversation(client, api_url, tenant_id, conv)
                    total_convs += c
                    total_msgs += m
                    total_rels += r
                except httpx.HTTPError as e:
                    errors += 1
                    summary = extract_conversation_summary(conv)
                    rprint(f"\n[red]Error ingesting {summary.id_short}:[/red] {e}")
                progress.advance(task)

    rprint(f"\n[green]✓ Ingestion complete[/green]")
    rprint(f"  Conversations: {total_convs}")
    rprint(f"  Messages: {total_msgs}")
    rprint(f"  Relations: {total_rels}")
    if errors:
        rprint(f"  [red]Errors: {errors}[/red]")

    if embed:
        rprint("\n[yellow]Embedding generation not yet implemented[/yellow]")


if __name__ == "__main__":
    app()
