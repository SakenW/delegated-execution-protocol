# Contributing

Thanks for improving the protocol.

Please keep changes evidence-based and narrow:

1. Explain the runtime behavior or failure mode being addressed.
2. Preserve the main conversation's final review and integration authority.
3. Add or update selector tests when routing behavior changes.
4. Update `evals/evals.json` for a new policy boundary or regression.
5. Run `PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py` before opening a pull request.

Do not add machine-specific paths, credentials, session transcripts, or unverified claims about a runtime's model-routing capability.
