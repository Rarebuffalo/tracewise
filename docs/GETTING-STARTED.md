# Getting started

Tracewise is a GitHub App you run yourself. When a GitHub Actions run fails, it reads the failed jobs' logs and the
code at the failing commit, asks **your** model provider (OpenAI or Gemini) to investigate with four read-only tools,
checks every claim against the evidence, and posts a short report on the commit or pull request. If the evidence is
not enough, it says "inconclusive" instead of guessing.

This page is the short path. Every step links to the detailed guide.

> **Pre-release.** The pipeline is heavily tested offline and has been run against live GitHub with a test model.
> The OpenAI and Gemini adapters follow the providers' recorded API contracts but have **not yet been run against the
> live APIs by this project**, and accuracy has not been measured. Try it on a test repository first.

## What you need

- A Linux server with Docker Engine and Compose v2.24+, a public DNS name, and inbound ports 80 and 443
  (GitHub only delivers webhooks to public HTTPS). A laptop works for a local trial
  ([SELF-HOSTING.md §3](SELF-HOSTING.md#3-local-trial-one-machine-nothing-exposed)).
- An API key for OpenAI or Gemini, and the exact model id you want to use.
- Permission to create a GitHub App on the account or organisation that owns your repositories.

## 1. Get the code and build the image

```bash
git clone https://github.com/Rarebuffalo/tracewise.git
```

```bash
cd tracewise && make image
```

## 2. Create the GitHub App

On GitHub: **Settings → Developer settings → GitHub Apps → New GitHub App**.

| Setting | Value |
|---|---|
| Webhook URL | `https://<your-domain>/webhooks/github` |
| Webhook secret | at least 16 random characters (you will put the same value in `web.env`) |
| Repository permissions | Actions **read**, Contents **read**, Metadata **read**, Pull requests **write**, Checks **write**. Nothing else. |
| Subscribe to events | `workflow_run` |

Generate a private key and save it. **Do not install the App yet.** Details: [SELF-HOSTING.md §7](SELF-HOSTING.md#7-github-app).

## 3. Write the secrets

Create a directory outside the repository (for example `/etc/tracewise`, mode 700) with one file per process, each
mode 600. The full table is in [SELF-HOSTING.md §6](SELF-HOSTING.md#6-configuration-and-secrets). The model settings
go in `worker.env`:

```
TW_ENV=prod
LLM_PROVIDER=openai            # or gemini
LLM_MODEL=<exact model id>     # required; there is no default
OPENAI_API_KEY=<your key>      # or GEMINI_API_KEY
DATABASE_URL=postgresql://tracewise_app:<password>@db:5432/tracewise
```

Every setting is explained in [CONFIGURATION.md](CONFIGURATION.md).

## 4. Start the stack

Follow steps 7–11 of [deploy/staging/README.md](../deploy/staging/README.md) (the folder name is historical; it is the
self-hosting bundle):

1. Start the database and create the three database roles.
2. Run the migrations.
3. Run the preflight. It must exit 0 and show `llm_provider: pass`.
4. Start `web`, `worker` and `proxy`, then check `https://<your-domain>/readyz` returns 200.

## 5. Install and try it

Install the App on **one test repository**, push a commit that makes a workflow fail, and wait a minute or two. You
should see a neutral Check Run named **Tracewise** on the commit, plus a commit comment (push) or a PR comment (pull
request). [SELF-HOSTING.md §8](SELF-HOSTING.md#8-what-a-first-test-shows) explains each possible outcome.

## What gets sent to your model provider

Redacted excerpts of the failed jobs' logs, the triggering diff and the source files the investigator chooses to read,
within fixed size limits ([DATA-INVENTORY.md](DATA-INVENTORY.md)). Redaction is pattern-based, so check your provider's
data-retention and training settings before using Tracewise on private code.

## Next

- Running it day to day (backups, upgrades, scheduled jobs): [SELF-HOSTING.md §10](SELF-HOSTING.md#10-operating-it).
- Something not working: [SELF-HOSTING.md §14](SELF-HOSTING.md#14-troubleshooting) and [OPERATIONS.md](OPERATIONS.md) §8a.
- Working on the code: [DEVELOPMENT.md](DEVELOPMENT.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).
