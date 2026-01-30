# ChatGPT Intake Script Requirements

## Purpose
Command-line script to process ChatGPT export files.

## Requirements
1. Read `conversations.json` from ChatGPT exports
2. Call Mímir API to ingest conversations into the service
3. Option to write each conversation to markdown files
4. **Start with**: Command-line option to identify/list each conversation in the file

## Input
- `chatgpt_export/conversations.json`

## Output Options
- List conversations (Phase 1)
- Export to markdown files
- Ingest to Mímir API
