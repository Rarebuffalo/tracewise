# Tracewise documentation

This directory is the single source of truth. `research/` holds the recorded model-API contracts and dated planning
notes; see [research/README.md](../research/README.md).

## Start here

| Document | Purpose |
|---|---|
| [GETTING-STARTED.md](GETTING-STARTED.md) | **The short path:** GitHub App, secrets, your model key, first run |
| [SELF-HOSTING.md](SELF-HOSTING.md) | The full self-hosting guide: local trial, server deployment with Docker Compose, upgrades, data handling, limitations |
| [CONFIGURATION.md](CONFIGURATION.md) | Every environment variable, its default and which process needs it |

## How it works

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and decisions (ADR-01…18), data model, security boundaries |
| [architecture/multi-provider-design.md](architecture/multi-provider-design.md) | Multi-provider model architecture: shared loop, native codecs, migration steps |
| [MODEL-ADAPTER.md](MODEL-ADAPTER.md) | Model adapter status, codec contract tests, open OpenAI and Gemini contract items |
| [SPEC.md](SPEC.md) | MVP requirements (FS-…), data contracts, validator rules |
| [DATA-INVENTORY.md](DATA-INVENTORY.md) | Every data category: source, purpose, storage, retention, evidence |
| [SECURITY-AUDIT.md](SECURITY-AUDIT.md) | Security audit findings SA-1 to SA-8 and evidence |
| [PRIVACY-NOTICE-DRAFT.md](PRIVACY-NOTICE-DRAFT.md) | Privacy notice **draft** (not legally reviewed), with its open items |

## Developing

| Document | Purpose |
|---|---|
| [DEVELOPMENT.md](DEVELOPMENT.md) | Local setup, running the processes, troubleshooting, glossary |
| [TESTING.md](TESTING.md) | Test commands, markers, layout, offline guarantees (network guard, no skips) |
| [BENCHMARK.md](BENCHMARK.md) | Synthetic cases B-01…B-17, tracks A–F, public-metadata cases, grading |
| [ACCEPTANCE-TESTS.md](ACCEPTANCE-TESTS.md) | Acceptance tests (AT-…) and the MVP gate |
| [TASKS.md](TASKS.md) | Dependency-ordered backlog with traceability |
| [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) | Gates A–E, package layout, analysis flow, configuration, controls |
| [DECISIONS.md](DECISIONS.md) | Closed decisions, applied defaults, open items |
| [CHANGELOG.md](CHANGELOG.md) | What changed, with validation results |
| [benchmark-runs/](benchmark-runs/) | Dated benchmark run records |

## Operating and validating

| Document | Purpose |
|---|---|
| [OPERATIONS.md](OPERATIONS.md) | Roles, App setup, worker/recovery/retention operation, incidents, release checklist |
| [DEPLOYMENT-BLUEPRINT.md](DEPLOYMENT-BLUEPRINT.md) | Vendor-neutral deployment design: processes, ingress, secrets, env inventory, database budget |
| [LIVE-VALIDATION-PLAN.md](LIVE-VALIDATION-PLAN.md) | Staged plan for validating against live GitHub in a test organisation |
| [LIVE-VALIDATION-RUNBOOK.md](LIVE-VALIDATION-RUNBOOK.md) | Test cards for tokens, intake, logs, a real provider, publication races and recovery |
| [SMOKE-RUNBOOK.md](SMOKE-RUNBOOK.md) | One controlled smoke check of the OpenAI API contract with your own key |
| [GITHUB-CONTRACT-AUDIT.md](GITHUB-CONTRACT-AUDIT.md) | GitHub platform assumptions versus recorded evidence and tests |
| [VALIDATION-PLAN.md](VALIDATION-PLAN.md) | Product validation plan (interviews, metadata-only checks) |

## Internal project records

Kept for the maintainer's planning and for history. They are not needed to use or contribute to Tracewise.

| Document | Purpose |
|---|---|
| [internal/PROJECT-HANDOFF.md](internal/PROJECT-HANDOFF.md) | Project state, remaining work and next actions |
| [internal/OWNER-DECISION-PACKET.md](internal/OWNER-DECISION-PACKET.md) | Consolidated open maintainer decisions |
| [internal/OWNER-DECISION-SHEET.md](internal/OWNER-DECISION-SHEET.md) | Plain-language list of decisions, with recommendations |
| [internal/DECISION-MEMOS.md](internal/DECISION-MEMOS.md) | P-2, P-3, C-CFG-1: canonical text, current behaviour, options and tests |
| [internal/DECISION-IMPLEMENTATION-PLAN.md](internal/DECISION-IMPLEMENTATION-PLAN.md) | Conditional plan per decision |
| [internal/RELEASE-CANDIDATE-V0.md](internal/RELEASE-CANDIDATE-V0.md) | V0 release candidate: commit plan, staging gates, acceptance matrix |
| [internal/BENCHMARK-REVIEW-QUEUE.md](internal/BENCHMARK-REVIEW-QUEUE.md) | Benchmark review items (proposals only; truth unchanged) |
| [internal/DOC-CHANGE-PLAN.md](internal/DOC-CHANGE-PLAN.md) | Documentation cleanup plan (change record) |
| [internal/HISTORY-REWRITE.md](internal/HISTORY-REWRITE.md) | The 2026-10-20 redaction rewrite and its commit hash map |

Project-level files: [../README.md](../README.md), [../CONTRIBUTING.md](../CONTRIBUTING.md),
[../SECURITY.md](../SECURITY.md), [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), [../LICENSE](../LICENSE).

**Commit hashes in dated records** may be stale: history was rewritten on 2026-10-20 (secret redaction, see
internal/HISTORY-REWRITE.md) and again on 2026-11-21 (removal of competitor research before open-sourcing).

**Rules that apply everywhere:**

- No personal, global or CLI GitHub credentials in code or tests. Benchmarks use synthetic data and anonymous public
  metadata only.
- No accuracy, latency or cost claims until measured (T-605).
- Live GitHub tests run only in a dedicated test organisation.

**Consistency check:** `python3 -I scripts/check_docs.py`
