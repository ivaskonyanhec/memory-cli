# memory add Design

**Goal:** Add a `memory add` command that imports a Markdown file into the Obsidian vault's `resources/` folder and immediately compiles that imported resource into the knowledge base.

**Command contract**
- Accept exactly one filesystem path argument: `memory add /path/to/file.md`.
- Reject missing paths, directories, and non-Markdown files.
- Copy the source file into `<vault>/resources/<basename>`.
- Refuse to overwrite an existing file in `resources/`.
- Compile only the imported file by invoking the compiler with `--file resources/<basename>`.

**Implementation shape**
- Add a new `add` command in `memory_cli/cli.py`.
- Keep path validation and import behavior in small helper functions rather than inlining everything in the command body.
- Reuse the existing compiler invocation pattern already used by `memory sync`.

**Error handling**
- Exit non-zero on validation failures, copy failures, or compiler failures.
- Print a direct CLI-facing error message for invalid input and filename collisions.

**Testing**
- Add CLI tests for:
  - successful import and compile invocation
  - missing source file
  - non-Markdown source
  - destination collision
- Mock configuration and compiler execution so tests stay local and deterministic.
