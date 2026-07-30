# Schema migrations

Comicarr schema changes are applied through reviewed Alembic revisions. Do not
use `metadata.create_all()` or startup repair code to alter a production
database.

## Normal startup

Startup classifies the configured database before it changes anything:

- An empty database upgrades from base to the current Alembic head.
- A database with `alembic_version` upgrades only when the table contains one
  exact revision from Comicarr's reviewed, single-head migration graph and the
  database contains the complete Comicarr schema required by **that stamped
  revision** (not the migration head). Tables first introduced by later
  revisions are optional until those upgrades run, so a pre-library-chat
  `0002` install is not blocked before `0003_library_chat` can create
  `ai_chat_*`. Empty, multiple, partial, unknown, or structurally spoofed
  revision states fail before schema mutation.
- A pre-Alembic Comicarr database is adopted only after it matches the
  conservative table, column, and `mylar_info` control-row fingerprint.
- Any other nonempty database is left untouched and worker startup is blocked.

When migration fails, the web process keeps its authenticated diagnostics
surface available while acquisition workers remain blocked. Fix the migration
state before releasing the maintenance gate.

Run a deployment migration with exactly one Comicarr process. For a scaled or
rolling deployment, scale workers down, run `upgrade head` once, verify the
revision, then start or scale the application back up. The application does not
coordinate concurrent migration leaders across separate processes.

## Operator workflow

1. Back up the database and verify the backup can be restored.
2. Set the normal `DATABASE_URL` or Comicarr configuration, then inspect the
   current revision:

   ```bash
   uv run alembic current
   ```

3. Apply reviewed revisions:

   ```bash
   uv run alembic upgrade head
   uv run alembic check
   ```

4. If adoption refuses a nonempty database, do not run `stamp` manually.
   Collect its table/column inventory and use an explicit repair or migration
   path. Automatic adoption intentionally fails closed.
   The same rule applies to an empty, multiple, partial, or unknown
   `alembic_version` state: preserve the database, inspect why its revision does
   not match Comicarr's graph, and use an explicit repair rather than forcing
   startup past the check.
5. If an upgrade is interrupted, leave workers blocked, restore the backup if
   needed, and rerun `upgrade head` only after confirming the database state.

Mylar imports and cross-database transfers bring their destination to Alembic
head before copying data, then verify that revision after the copy. They must
not drop indexes and rely on startup to recreate them.
