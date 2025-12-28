-- Migration 009 down: Remove Ollama embedding models from enum
-- Note: PostgreSQL doesn't support removing enum values directly
-- This is a no-op - enum values can only be removed by recreating the type
-- which would require recreating all dependent tables

-- If you need to actually remove these values, you'd need to:
-- 1. Create a new enum without these values
-- 2. Update all tables using the enum to use the new type
-- 3. Drop the old enum
-- This is destructive and usually not worth doing

DO $$
BEGIN
    RAISE NOTICE 'Cannot remove enum values in PostgreSQL. Migration 009 down is a no-op.';
END
$$;
