-- Waitlist runtime role. TEMPLATE for review: run ONCE as the database owner/administrator, BEFORE the waitlist
-- migration (python -m tracewise.waitlist.migrate upgrade), which grants this role its table rights.
--
-- The role has no password here: set one in your database console (or `ALTER ROLE ... PASSWORD`) and put the
-- resulting connection string in WAITLIST_DATABASE_URL on the backend only. Never commit it.
--
-- What it can do: SELECT/INSERT/UPDATE/DELETE on the five tables in schema `waitlist`.
-- What it cannot do: create objects, read the product schema or any other table, bypass row security, create roles.
CREATE ROLE tracewise_waitlist LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- Defence in depth on a shared database (PostgreSQL 15+ already removes CREATE on public from PUBLIC).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
