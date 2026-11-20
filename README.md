# Delegated Execution Protocol

A decision protocol and deterministic selector for delegating agent work without turning every task into a swarm.

It begins with a cold-start value gate, assigns the smallest adequate agent profile only when delegation is justified, keeps review authority with the main conversation, and makes transport verification explicit.

The protocol is written primarily in Chinese; the scripts and structured output are language-neutral.

## What it enforces

- Keep trivial, sequential work in the main conversation.
- Require a concrete reason before starting a worker: independent evidence, a batch of at least 10 homogeneous items, bounded ownership, critical-path parallelism, or live steering.
- Reject incompatible task-kind/write combinations before routing them to a worker.
- Separate read-only review from writes, with explicit main-thread acceptance between them.
- Cap one-off and batch concurrency at two workers; batches default to one unless throughput evidence justifies sharding.
- Treat declared model labels as untrusted until the runtime proves the actual model, reasoning effort, and transport.
- Fail closed if a requested model/effort is unavailable.
- Use `delegated_standard_reviewer` for bounded low- or medium-risk reviews with verifiable evidence, and `delegated_reviewer` for high-risk, cross-module or contract-sensitive reviews. See the [model policy](references/model-policy.md) for the current bindings.

## Repository layout

- `SKILL.md` — the protocol used by an agent.
- `scripts/select_agent_profile.py` — deterministic routing selector that emits JSON.
- `scripts/test_select_agent_profile.py` — behavior tests for the selector.
- `scripts/test_validate_protocol.py` — fail-closed tests for static/manual contract validation.
- `scripts/validate_protocol.py` — structure, safety, and behavior validation.
- `evals/evals.json` — scenario-based evaluation set.
- `references/` — concise transport and reporting contracts.

## Quick start

Set the computer runtime directory in
`$CODEX_HOME/delegated-execution-protocol-runtime.path` (`$CODEX_HOME` defaults
to `~/.codex`). The file contains one absolute directory path. That directory
provides `run_computer_task.py` and `test_run_computer_task.py` to the skill's
entry points, including after deployment with Skills Manager. Use the [guarded sync command](CONTRIBUTING.md#sync-the-local-skills-manager-installation) when refreshing this skill.

With the runtime files in place, run the protocol validation:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py
```

The validator executes selector routes and controlled file/token checks for manual contracts. Those static checks prove that required policy text remains present; they are explicitly not end-to-end agent-runtime evidence.

To route a task, describe its observable properties rather than guessing a model first:

```bash
python3 scripts/select_agent_profile.py \
  --kind implementation --writes bounded --scope medium \
  --task-size medium --risk low --ambiguity low \
  --independent-evidence none --parallel-value useful \
  --priority economy --workload one-off --batch-size 1 \
  --verification strong --sensitivity none --coordination isolated \
  --steering-trigger none --requested-workers 1 \
  --sharding-evidence none --transport-preference auto
```

The JSON result is a recommendation and policy decision. Before dispatch, verify that the selected transport can actually enforce the returned profile. Under `auto`, missing or mismatched native evidence stops steerable work. Isolated computer tasks use the explicit app-server, and other isolated tasks use the explicit CLI. Native evidence must include a matching provider when the role or global configuration specifies one.

## Optional local-installation check

Both validation modes run the computer client regression suite through the runtime path configured above, including on a clean checkout or runner. The default uses fixtures for agent profiles and the model catalog. To also check the installed profiles and catalog, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py --check-local-profiles
```

The extra check reads the selected Codex home (override with `--codex-home`). It checks every protocol role against its registered profile or standalone role file and the configured model catalog (default `models_cache.json`). The runtime path for the computer tests still comes from `CODEX_HOME`.

## Installation as a Codex skill

Place this directory in a configured Codex skill-discovery root, keeping the layout intact. The protocol deliberately does not prescribe a single global install path: each team should use its own skill ownership and discovery conventions.

## Scope and limitations

This repository provides a policy and reference implementation, not a guarantee about any agent runtime. Models, available reasoning levels, sandbox semantics, and child-process metadata vary by product version and deployment. Re-probe your transport after upgrades before claiming that a routed profile was actually applied.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security-sensitive issues should follow [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
