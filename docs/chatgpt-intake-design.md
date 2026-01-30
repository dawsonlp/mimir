# ChatGPT Intake Script Design

## Script Location
`scripts/ingest_chatgpt.py`

## Dependencies
- **typer** - CLI framework with type hints
- **rich** - Beautiful terminal output, progress bars, tables

## CLI Interface

Designed for extensibility. Initial commands are `list`, `export`, and `ingest`. Additional commands can be added as the tool evolves.

### Command Structure
```
python scripts/ingest_chatgpt.py <command> [options] <file>
```

### Commands

#### list
Display conversations in the export file.

```
python scripts/ingest_chatgpt.py list conversations.json
python scripts/ingest_chatgpt.py list conversations.json --json
python scripts/ingest_chatgpt.py list conversations.json --filter "python"
```

Options:
- `--json` - Output as JSON instead of human-readable
- `--filter TEXT` - Filter by title (case-insensitive substring)
- `--limit N` - Show only N conversations

Output:
```
ChatGPT Export: 1070 conversations

  1. [694ef4c7] Extensible Chat UI Solutions (8 msgs) 2025-12-29
  2. [abc12345] Python Async Patterns (24 msgs) 2025-12-28
  ...
```

#### export
Write conversations to markdown files.

```
python scripts/ingest_chatgpt.py export conversations.json --output-dir ./md
python scripts/ingest_chatgpt.py export conversations.json --id 694ef4c7
```

Options:
- `--output-dir PATH` - Directory for markdown files (default: `./chatgpt_md`)
- `--id PREFIX` - Export single conversation by ID prefix
- `--filter TEXT` - Filter by title

#### ingest
Send conversations to Mímir API.

```
python scripts/ingest_chatgpt.py ingest conversations.json
python scripts/ingest_chatgpt.py ingest conversations.json --dry-run
```

Options:
- `--api-url URL` - API base URL (default: `http://localhost:38000/api/v1`)
- `--tenant-id N` - Tenant ID (default: 1)
- `--id PREFIX` - Ingest single conversation
- `--filter TEXT` - Filter by title
- `--dry-run` - Show what would be created without calling API
- `--embed` - Create embeddings after ingestion

## Markdown Format

Filename: `{date}_{title}_{id}.md`
- date: YYYY-MM-DD from create_time
- title: lowercase, spaces to hyphens, max 50 chars
- id: first 8 characters of conversation ID

Example: `2025-12-29_extensible-chat-ui-solutions_694ef4c7.md`

Content:
```markdown
# Extensible Chat UI Solutions

**ID:** 694ef4c7-6f90-8332-bc6a-5339ffb8a9d4  
**Created:** 2025-12-29 14:31:50 UTC

---

## User
*14:31:50*

Noi gets part of the way there...

---

## Assistant
*14:31:51*

Here are some existing solutions...
```

## Mímir API Mapping

### Artifact Types
- `conversation` - Parent artifact for each ChatGPT conversation
- `message` - Child artifact for each message in the conversation

### Conversation → Artifact
| ChatGPT | Mímir Artifact |
|---------|----------------|
| id | external_id |
| title | title |
| - | artifact_type = "conversation" |
| - | source = "chatgpt" |
| - | source_system = "chatgpt_export" |
| create_time | metadata.create_time |
| update_time | metadata.update_time |
| is_archived | metadata.is_archived |

### Message → Artifact
| ChatGPT | Mímir Artifact |
|---------|----------------|
| message.id | external_id |
| "{role}: {content preview}" | title |
| - | artifact_type = "message" |
| - | parent_artifact_id = conversation artifact id |
| content.parts joined | content |
| - | source = "chatgpt" |
| author.role | metadata.author_role |
| create_time | metadata.create_time |
| metadata.model_slug | metadata.model |
| sequence number | position_metadata.sequence |

### Relations
| Type | Source | Target |
|------|--------|--------|
| contains | conversation | message |
| follows | message N | message N-1 |

## Processing Flow

### list command
1. Open and parse JSON file
2. For each conversation: extract id, title, create_time, count messages
3. Apply filter if specified
4. Sort by create_time descending
5. Output to console

### export command
1. Parse JSON file
2. Filter conversations
3. For each conversation:
   - Traverse tree from current_node to root
   - Reverse to chronological order
   - Filter out system messages with empty content
   - Generate markdown
   - Write to file

### ingest command
1. Parse JSON file
2. Ensure tenant exists
3. For each conversation:
   - Create conversation artifact
   - Traverse and create message artifacts
   - Create relations
4. Report summary

## Error Handling

- File not found: Exit with error
- Invalid JSON: Exit with error
- Empty conversations: Warning, continue
- API errors: Log and continue to next conversation
- Missing fields: Use defaults, log warning
