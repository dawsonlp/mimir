-- Extensions needed by Mimir
-- All extensions are pre-installed in dawsonlp/postgres-batteries-inc:18
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

-- AGE types (agtype, graphid) and operators (graphid_ops) live in ag_catalog.
-- Add ag_catalog to the database search_path so these are resolvable in every
-- session without an explicit SET search_path command.
ALTER DATABASE mimir SET search_path = public, ag_catalog;
