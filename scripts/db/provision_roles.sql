-- Tracewise database roles (T-705, D-11). TEMPLATE for review: run by a database administrator as a superuser,
-- ONCE, before the first migration. It creates roles WITHOUT passwords: authentication (passwords, certificates,
-- IAM) and credential storage are a deployment decision (D-11) and are deliberately not in this file.
-- The test suite runs this exact file against a disposable cluster (tests/db/test_fresh_install.py).

-- Migration owner: owns the schema and runs migrations. Not a superuser, so the SECURITY DEFINER purge function
-- it owns carries only table-owner rights.
CREATE ROLE tracewise_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- Tenant plane (DATABASE_URL): row-level security always applies.
CREATE ROLE tracewise_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- System plane (DATABASE_URL_SYSTEM): ingress, lifecycle, queue, recovery, retention. Bypasses RLS by design.
CREATE ROLE tracewise_system LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;

CREATE DATABASE tracewise OWNER tracewise_owner;
-- Hardening (SA-5 defence in depth): runtime roles need no temporary tables and may not create objects.
\connect tracewise
REVOKE TEMPORARY ON DATABASE tracewise FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
