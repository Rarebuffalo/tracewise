# Privacy notice: DRAFT for review (T-1001)

> **Status: draft, not approved, not published.** This text describes only behaviour present in the code at the Phase 23 commit. The detail and evidence are in [DATA-INVENTORY.md](DATA-INVENTORY.md).
>
> It must not be published until:
> - the open items in §10 are resolved;
> - the bracketed placeholders are filled by the owner;
> - legal review is complete.
>
> It contains no legal basis, jurisdiction, certification or contractual commitment; those are for the owner and counsel to supply.

---

## Tracewise privacy notice (pilot)

**Who we are:** [OWNER / LEGAL ENTITY: to be supplied]. **Contact:** [CONTACT ADDRESS: to be supplied].

### 1. What Tracewise is

Tracewise is a GitHub App that analyses failed GitHub Actions runs in repositories where you install it, and posts a diagnosis back to that repository.

### 2. Data we receive

When the App is installed, GitHub sends Tracewise:
- events about installations;
- events about the repositories you grant;
- events for completed workflow runs.

For a failed run, Tracewise then retrieves, using a short-lived token limited to that one repository:
- the run's job metadata and logs;
- the changes in the triggering commit;
- the specific source files it needs to read.

It requests only these permissions: Actions read, Contents read, Metadata read, Pull requests write, Checks write.

### 3. How we use it

To identify the error in the logs, to investigate the related source code, and to publish a diagnosis as a commit comment, PR comment or Check Run. Every location and excerpt in a diagnosis is checked against the logs and code before publication.

### 4. Model provider

[**Pending T-605 / UD-3.**] Analysis uses an AI model from [PROVIDER: planned OpenAI; not yet enabled], model family [MODEL FAMILY: to be chosen].

When enabled, the following are sent to that provider:
- excerpts of your logs, with secret-like values redacted;
- the changes in the triggering commit;
- the portions of source files the investigator reads (up to 250 lines per read), **sent as they are in your repository** [pending P-2: redaction of source before sending].

The model cannot run commands, change files or reach other systems. It can only request reads through four read-only tools, and its output is validated before anything is published. [Provider data-retention and training terms: to be stated once the provider contract is recorded (MODEL-ADAPTER C-8).]

### 5. What we store, and for how long

**We do not store:**
- your full logs;
- your full source files;
- webhook payload bodies;
- access tokens.

**We do store:**

| Data | Retention |
|---|---|
| Installation and repository identifiers and names | Until 7 days after you uninstall, then deleted, except a minimal record of the installation id and its deleted status |
| Run identifiers and metadata | Up to 365 days |
| The diagnosis, including redacted log excerpts (≤2 KB each), a redacted snippet of up to 15 source lines at the identified location [size limit pending P-3], and the proposed fix | The diagnosis content is cleared after 90 days; the remaining analysis metadata after 180 days |
| Error fingerprints (short, redacted messages) and usage and audit records | Up to 365 days |

[These periods are pending approval: D-12.]

**Reports already posted to your repository** are stored by GitHub under your control. Uninstalling Tracewise does not remove them.

### 6. Logs and telemetry

Operational logs contain event names, identifiers, outcomes, counts and timings. They are designed not to contain repository content, and secret-like values are scrubbed.

### 7. Isolation and access

Each installation's data is separated in the database by row-level security. Analysis runs under a database role that can see only the installation being analysed. [Operator access controls, hosting location and backup handling: to be supplied with the deployment (T-1002).]

### 8. Other services

- GitHub (APIs and git);
- GitHub's log storage (blob URLs GitHub provides);
- the model provider in §4, once enabled;
- [hosting and database providers: to be supplied].

### 9. Your choices

You can choose which repositories the App can access, suspend it, or uninstall it at any time. Uninstalling stops analysis immediately and schedules deletion as described in §5. [Requests for earlier deletion or access: process to be defined.]

### 10. Open items before publication (not part of the notice)

| # | Item | Owner |
|---|---|---|
| 1 | Legal entity, contact, jurisdiction, legal basis, any processor or sub-processor terms | Owner, counsel |
| 2 | Provider and model family (AT-SEC-13 requires both) | T-605, UD-3 |
| 3 | Provider retention and training terms (MODEL-ADAPTER C-8) | T-605 |
| 4 | Retention periods and tombstone/audit behaviour | D-12 |
| 5 | Whether source sent to the provider should be redacted first (P-2) | Your decision |
| 6 | Hosting, region, backups, operator access | T-1002 |
| 7 | Process for early deletion and access requests | Owner |
| 8 | Pilot terms template (also part of T-1001): **not drafted**, because it is a contractual document | Owner, counsel |
