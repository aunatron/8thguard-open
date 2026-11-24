# Contributing to 8thGuard Open

Thank you for contributing to open, verifiable evidence tooling for digital assets and autonomous agents.

## Guidelines

1. **Keep boundaries strict:** All adapters in `packages/network-evidence` must stay strictly read-only, bounded in timeout and payload size, and explicit about unknowns. Never add custody, private-key handling, or black-box safety verdicts.
2. **Test offline:** Every pull request must include deterministic offline tests (`node --test` or `pytest` with mocked transports) that pass with zero external credentials.
3. **Zero PII or secrets:** Never commit API keys, `.env` files, private keys, or personal data.
4. **Licensing:** Code contributions in `packages/` and `contracts/` are accepted under the **Apache License 2.0** (`LICENSE`). Synthetic benchmark and Field Note contributions under `benchmarks/` are accepted under **CC-BY-4.0** (`DATA_LICENSE`).
