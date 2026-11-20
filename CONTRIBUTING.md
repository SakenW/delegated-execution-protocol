# Contributing

Thanks for improving the protocol.

Please keep changes evidence-based and narrow:

1. Explain the runtime behavior or failure mode being addressed.
2. Preserve the main conversation's final review and integration authority.
3. Add or update selector tests when routing behavior changes.
4. Update `evals/evals.json` for a new policy boundary or regression.
5. Run `PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py` before opening a pull request.

Do not add machine-specific paths, credentials, session transcripts, or unverified claims about a runtime's model-routing capability.

## Sync the local Skills Manager installation

After validating and committing a candidate, run the guarded update from the source checkout:

```bash
python3 -B scripts/sync_skills_manager.py --baseline <last-verified-synchronized-source-commit>
```

Use the source commit last verified against the installed copy, including when several commits have accumulated. Add `--check-only` for a read-only preflight. The command compares the Manager library with that baseline and the source checkout with HEAD. It reports missing, extra and modified paths, including ignored files, and checks executable bits and symbolic links. A failed preflight stops before the update. Inspect the reported paths before retrying. After a successful update the command verifies the library against the candidate commit.
