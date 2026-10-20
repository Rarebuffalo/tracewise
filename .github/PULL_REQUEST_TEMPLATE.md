## Summary

<!-- What changes and why. Link the issue, spec item (FS-…/AT-…) or decision (D-…) if there is one. -->

## Implementation

<!-- The approach, and anything a reviewer should look at closely. -->

## Tests and checks

- [ ] Regression test added first for a bug fix (it failed before the fix)
- [ ] `make check`
- [ ] `PYTHONPATH=. uv run pytest -q -p no:cacheprovider -p tests.netguard -m "not live" -rs` (0 network attempts, no skips)
- [ ] `uv run python -m tracewise.bench verify`
- [ ] `git diff --check`

## Security and tenant isolation

<!-- Effect on webhook verification, GitHub permissions, RLS/roles, the read-only investigator, redaction,
     escaping, logging. Write "none" if none. -->

## Migration and configuration

<!-- New migration (with downgrade)? New or changed settings? Grants (update the privilege matrix)? Write "none" if none. -->

## Documentation

<!-- Docs and CHANGELOG updated, or why not needed. -->

## Confirmation

- [ ] No secrets, tokens, keys, signed URLs, private code or private logs are included
- [ ] No protected research evidence was opened or changed, and benchmark truth / `TRUTH.lock` are unchanged
- [ ] No live external calls were added to tests
