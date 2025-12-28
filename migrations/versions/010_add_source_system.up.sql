-- Migration 010: Add source_system for external key provenance
-- This allows proper compound lookup: source_system + external_id = unique external reference

-- Add source_system column to track which external system an external_id came from
-- Examples: "chatgpt", "notion", "github", "obsidian", "raindrop", "pocket", etc.
ALTER TABLE mimirdata.artifacts
ADD COLUMN source_system TEXT;

-- Add comment for documentation
COMMENT ON COLUMN mimirdata.artifacts.source_system IS 'External system identifier (e.g., chatgpt, notion, github) used with external_id for provenance';
COMMENT ON COLUMN mimirdata.artifacts.source IS 'General source category (e.g., file, api, import)';
COMMENT ON COLUMN mimirdata.artifacts.external_id IS 'Original ID in the source_system (e.g., ChatGPT conversation UUID)';

-- Create index for efficient lookups by source_system + external_id
CREATE INDEX idx_artifacts_source_system_external_id 
ON mimirdata.artifacts (source_system, external_id)
WHERE source_system IS NOT NULL AND external_id IS NOT NULL;

-- Create index for filtering by source_system alone
CREATE INDEX idx_artifacts_source_system 
ON mimirdata.artifacts (source_system)
WHERE source_system IS NOT NULL;
