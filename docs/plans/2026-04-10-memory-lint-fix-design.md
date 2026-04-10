# memory lint-fix Design

**Goal:** Add a `memory lint-fix` command that safely repairs deterministic structural issues in the knowledge base, starting with missing backlinks.

**Command contract**
- Add `memory lint-fix` as a separate command from `memory lint`.
- Support `--dry-run` to preview planned edits without writing files.
- Apply only safe structural fixes in v1.
- Limit v1 scope to the `missing_backlink` rule.

**Behavior**
- Scan knowledge articles in the configured knowledge folder.
- Detect asymmetric links: if article A links to B and B exists but does not link back to A, mark it fixable.
- Add the backlink to the target article without duplicating an existing link.
- Prefer appending to an existing `## Related Concepts` section; otherwise create one at the end.

**Safety rules**
- Do not use any LLM/provider for `lint-fix` v1.
- Do not rewrite sparse articles, contradictions, or broken links.
- Keep edits idempotent.

**Testing**
- Cover:
  - one-way link becomes two-way after `lint-fix`
  - `--dry-run` reports the change without editing
  - second run is a no-op
