# Host marketplace contracts

This repository carries a repo-scoped Codex marketplace descriptor at
`.agents/plugins/marketplace.json`. It describes the existing
`.codex-plugin/plugin.json` package; it does not install the plugin, change a user
configuration or cache, publish a listing, or prove that any external marketplace is
enabled.

The sole Codex entry is `agy-worker`. Its `source.source` is `local` and its
`source.path` is exactly `.`. The package is therefore the repository root: its name
must equal `.codex-plugin/plugin.json`'s `name`, and it uses the one canonical
`skills/agy-worker/` bundle and its bundled `runtime/`. Do not introduce a
`plugins/` copy, a second skill source, or a second runtime to satisfy marketplace
layout conventions.

The packaging contract rejects a missing or symlinked plugin manifest, a mismatched
name, alternate or escaping source paths, duplicate skill/runtime trees, and changed
installed runtime bytes. `install.sh` remains the explicit local skill-installation
path; its copied skill bundle must remain byte-identical to the source bundle (apart
from the local `.pipeline-root` marker).

Review the repository source, then add its Git-backed Codex marketplace and install
the plugin with:

```bash
codex plugin marketplace add cagdasyurekli/agy-worker
codex plugin add agy-worker@agy-worker
```

Start a new Codex session after installation. This enables the local plugin only; it
does not authorize a provider call or transmission of repository content. Before
dispatch, the skill still requires approval for the exact transmission mode and
content. Prefer `--provider-scope` for bounded jobs: it binds exact reviewed read/write
entries and selected content, then stages only selected entries in a fresh owner-private
mode-`0700` Gitless provider cwd. Whole-worktree dispatch remains an explicit
`--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception, binding the manifest and
execution mode, and may send the entire disposable
worktree through `agy` to Google/Gemini. The controller still validates local worktree paths,
and new jobs default to `--provider-isolation session`, with normal user filesystem
and network access. Explicit native mode adds scoped macOS containment with the
documented network and process-group limits. Scope selection alone grants no Git
action, acceptance, or publication. Secrets, denied paths, and unrelated private files
must be absent from all content approved for either mode.

Validate the package manifest before a release-oriented review with the installed
plugin-creator skill's `scripts/validate_plugin.py`, passing this repository root as
its argument. For example, from that skill directory:

```bash
python3 scripts/validate_plugin.py <repository-root>
```

That validator is local package-shape evidence only. Before documenting the commands
above, the repository was also fetched at an immutable public Git commit in disposable
Codex state; marketplace add/list, plugin install/remove, resolver discovery, and
source-installed skill parity passed. This does not prove future snapshots, provider
behavior, task quality, or general correctness.

## Claude Code catalog

`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` both name
`agy-worker`, with versions synchronized to the Codex manifest and skill metadata.
The Claude marketplace entry uses `source: "./"`, so the repository root supplies
the same `skills/agy-worker/` bundle. No hooks, MCP servers, commands, or agent
components are declared. Claude discovers the skill as `/agy-worker:agy-worker`.

Claude Code host operation was live-tested with synthetic jobs. Packaging tests
validate JSON shape and resolver layouts offline; they do not prove a future install
or provider result. Use `claude plugin validate .` and the local steps in
[Installation](INSTALLATION.md#claude-code) for the selected source.
The [Claude marketplace reference](https://code.claude.com/docs/en/plugin-marketplaces)
describes root-relative sources and validation. No catalog submission is part of a
repository edit. Review the selected source and installed bytes for each new snapshot.
