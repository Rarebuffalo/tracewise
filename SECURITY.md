# Security policy

## Supported versions

Tracewise has **no release** yet (`version = "0.0.1"` in `pyproject.toml`, pre-release). Only the latest commit on
`main` is supported. Security fixes land there; there are no maintained release branches.

## Reporting a vulnerability

**Please do not report security problems in public issues, pull requests or discussions.** Do not publish working
exploits, credentials, tokens, signed URLs, private repository code, or CI logs from private repositories anywhere
public.

Report privately instead:

1. Use GitHub's **private vulnerability reporting** for this repository (the repository's **Security** tab →
   **Report a vulnerability**), if it is enabled.
2. If it is not available, contact the maintainer, [@Rarebuffalo](https://github.com/Rarebuffalo), privately
   through GitHub. Ask for a private channel first, and do not include the vulnerability details in a public message.

Please include:
- the affected component and commit;
- the impact you believe it has;
- minimal reproduction steps, using synthetic data only;
- whether you think it is being exploited.

There is no bug bounty, no formal response-time commitment and no dedicated security team. This is a small,
pre-release project. Reports will be read and answered on a best-effort basis, and fixes will be credited if you
wish.

## Scope

In scope:
- **Webhook ingestion:** signature verification, size limits, event validation.
- **GitHub credential handling and scopes:** App JWT, installation tokens, the requested permissions.
- **Tenant isolation:** PostgreSQL row-level security, role separation, installation-scoped keys.
- **Investigation sandbox:** the four read-only tools, path confinement, size and time limits.
- **Model input and output handling:** redaction before the provider, validation of model output, prompt-injection
  containment.
- **Report rendering:** escaping, link and mention neutralisation, report markers.
- **Secret handling** in logs, errors and stored data.
- **The offline smoke harness's safeguards** (`scripts/openai_smoke.py`).

Out of scope:
- vulnerabilities in GitHub, OpenAI or other third-party services themselves;
- findings that need a compromised host or database administrator;
- the dated research and evidence under `research/`, which is not executed.

## Known limitations

These are documented, so they are not new findings, but improvements are welcome:

- **Redaction is pattern-based.** Encoded, split or unfamiliar secret formats can pass through to logs, the model
  provider or stored snippets.
- **Code running as the tenant database role can set any tenant id itself.** Row-level security protects against
  query mistakes and payload confusion, not against arbitrary SQL execution inside the service.
- **No live validation yet.** GitHub behaviour (permissions, suspended installations, limits) and model behaviour
  (injection resistance) are verified only against fakes and recorded documentation.

The detailed threat analysis, findings SA-1 onward and their evidence are in
[docs/SECURITY-AUDIT.md](docs/SECURITY-AUDIT.md). The security boundaries are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §4, and the data handled is in
[docs/DATA-INVENTORY.md](docs/DATA-INVENTORY.md).
