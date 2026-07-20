# Delegated Execution Protocol

A decision protocol and deterministic selector for delegating agent work without turning every task into a swarm.

It begins with a cold-start value gate, assigns the smallest adequate agent profile only when delegation is justified, keeps review authority with the main conversation, and makes transport verification explicit.

The protocol is written primarily in Chinese; the scripts and structured output are language-neutral.

## What it enforces

- Keep trivial, sequential work in the main conversation.
- Require a concrete reason before starting a worker: independent evidence, an amortized batch, bounded ownership, critical-path parallelism, or live steering.
- Separate read-only review from writes, with explicit main-thread acceptance between them.
- Cap one-off and batch concurrency at two workers; batches default to one unless throughput evidence justifies sharding.
- Treat declared model labels as untrusted until the runtime proves the actual model, reasoning effort, and transport.
- Fail closed if a requested model/effort is unavailable.

## Repository layout

- `SKILL.md` — the protocol used by an agent.
- `scripts/select_agent_profile.py` — deterministic routing selector that emits JSON.
- `scripts/test_select_agent_profile.py` — behavior tests for the selector.
- `scripts/validate_protocol.py` — structure, safety, and behavior validation.
- `evals/evals.json` — scenario-based evaluation set.
- `references/` — concise transport and reporting contracts.

## Quick start

Clone the repository, then run the self-contained validation:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py
```

To route a task, describe its observable properties rather than guessing a model first:

```bash
python3 scripts/select_agent_profile.py \
  --kind implementation --writes bounded --scope medium \
  --task-size medium --risk low --ambiguity low \
  --independent-evidence none --parallel-value useful \
  --priority balanced --workload one-off --batch-size 1 \
  --verification strong --coordination isolated \
  --steering-trigger none --requested-workers 1 \
  --sharding-evidence none --transport-preference auto
```

The JSON result is a recommendation and policy decision. Before dispatch, verify that the selected transport can actually enforce the returned profile. If it cannot, either use an enforcing isolated transport or report the inherited runtime configuration accurately.

## Optional local-installation check

The default validator is portable and does not inspect your home directory. If you maintain the corresponding Codex profile files locally, opt in to that extra check:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py --check-local-profiles
```

This expects `~/.codex/config.toml`, `~/.codex/models_cache.json`, and profiles named by `EXPECTED_PROFILES` in `scripts/validate_protocol.py`.

## Installation as a Codex skill

Place this directory in a configured Codex skill-discovery root, keeping the layout intact. The protocol deliberately does not prescribe a single global install path: each team should use its own skill ownership and discovery conventions.

## Scope and limitations

This repository provides a policy and reference implementation, not a guarantee about any agent runtime. Models, available reasoning levels, sandbox semantics, and child-process metadata vary by product version and deployment. Re-probe your transport after upgrades before claiming that a routed profile was actually applied.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security-sensitive issues should follow [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
