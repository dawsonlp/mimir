# ChatGPT Intake Script Analysis

## Source File
`chatgpt_export/conversations.json`

## Data Structure

### conversations.json
Array of Conversation objects. Current export contains 1,070 conversations.

### Conversation
| Field | Type | Description |
|-------|------|-------------|
| id | UUID string | Unique conversation identifier |
| conversation_id | UUID string | Duplicate of id |
| title | string | User-visible conversation title |
| create_time | float | Unix timestamp with fractional seconds |
| update_time | float | Unix timestamp of last modification |
| is_archived | boolean | Whether user archived the conversation |
| current_node | UUID string | Reference to the most recent message node |
| mapping | Dictionary<UUID, Node> | Tree structure containing all messages |

### Node
Represents a position in the message tree. The `mapping` dictionary uses node UUIDs as keys.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID string | Node identifier (matches dictionary key) |
| parent | UUID string or null | Reference to parent node |
| children | Array of UUID strings | References to child nodes |
| message | Message or null | Message content (null for structural nodes) |

### Message
Contains the actual content of a user or assistant turn.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID string | Message identifier |
| author | Author | Who sent this message |
| create_time | float or null | Unix timestamp |
| update_time | float or null | Unix timestamp |
| content | Content | Message payload |
| status | string | Processing status (e.g., "finished_successfully") |
| end_turn | boolean or null | Whether this ended a turn |
| weight | float | Display priority (1.0 = visible, 0.0 = hidden) |
| metadata | Dictionary | Model info, request IDs, etc. |
| recipient | string | Message routing (usually "all") |
| channel | string or null | Communication channel |

### Author
| Field | Type | Description |
|-------|------|-------------|
| role | string | "user", "assistant", or "system" |
| name | string or null | Display name |
| metadata | Dictionary | Additional author info |

### Content
| Field | Type | Description |
|-------|------|-------------|
| content_type | string | Type discriminator (e.g., "text") |
| parts | Array of strings | Content segments (for text type) |

## Tree Structure Characteristics

1. **Root**: The tree starts at a node with `parent: null`, typically named "client-created-root"

2. **Branching**: Multiple children indicate regenerated responses or conversation branches. ChatGPT allows users to regenerate assistant responses, creating alternative branches.

3. **Main Path**: The `current_node` field on Conversation points to the leaf of the active branch. Following parent links from `current_node` to root gives the displayed conversation.

4. **System Messages**: Nodes with `author.role: "system"` are typically hidden (`weight: 0.0`) and contain empty content. These handle internal ChatGPT state.

5. **Traversal**: To reconstruct a conversation:
   - Start at `current_node`
   - Follow `parent` links to root
   - Reverse to get chronological order
   - Filter by `weight > 0` and `author.role != "system"` for visible messages
