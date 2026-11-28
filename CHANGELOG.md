# Changelog

All notable changes to the 8thGuard Open Verification Toolkit are documented here.

## [Unreleased]

### Added
* `contracts/evidence-registry`: Added allowlisted `--network celo-mainnet` (chain `42220`, `https://forno.celo.org`) and `--network base-mainnet` (chain `8453`, `https://mainnet.base.org`) support plus optional ERC-8021 Schema 0 Builder Code data-suffix attribution (`scripts/erc8021.mjs`, `--builder-code`) to `scripts/operator.mjs` alongside default `xdc-apothem` (chain `51`), added zero-PII synthetic benchmark anchoring helpers `scripts/celo-demo-deploy.mjs` and `scripts/base-demo-deploy.mjs`, and added self-contained local Anvil chain `42220` and `8453` end-to-end tests (`npm run test:celo`, `npm run test:base`).

## [0.1.1] - 2026-11-25

### Added
* `packages/network-evidence`: Read-only `ERC-3643` (T-REX) tokenised real-world asset (RWA) preflight inspector (`inspect_erc3643` + `ERC3643_SELECTORS`) checking chain ID, contract bytecode, pause status, `ONCHAINID` identity registry, compliance module, holder freeze status, partial frozen balances, and recipient verification with explicit unknowns and deterministic offline mocked-RPC unit tests (`tests/test_rwa_erc3643.py`).
* `packages/network-evidence/examples/erc3643_rwa_inspect.py`: Standalone CLI example for read-only ERC-3643 RWA token inspection across configured EVM networks (including Base, Celo, Ethereum, and XDC).
* `benchmarks/field-notes/FN-004-erc3643-rwa-freeze-and-identity-gap.json`: Synthetic CC-BY-4.0 benchmark fixture documenting ERC-3643 freeze and recipient identity blind spots.
* `CODE_OF_CONDUCT.md` and Digital Public Good alignment documentation (SDG 4/9/16, platform independence, privacy boundaries, and verifiable DPC Ghana Privacy Seal reference).

## [0.1.0] - 2026-11-24

### Added
* Initial standalone public release extracted cleanly for independent verification and open-source maintenance.
* `packages/receipt-verifier`: Zero-dependency Node 24 / Web Crypto Ed25519 canonical JSON verifier (`cli.mjs`, `index.mjs`) with tamper, expiry, and unknown offline lifecycle tests.
* `packages/network-evidence`: Bounded read-only transaction observation adapters covering 14 EVM, Solana, and Stellar network configurations with offline unit tests and the standalone `examples/vet402_join_verify.py` HTTP 402 settled-4xx verification script.
* `contracts/evidence-registry`: Solidity `0.8.36` opaque SHA-256 commitment and expiry registry under Apache-2.0 with reproducible compilation scripts and Anvil lifecycle tests.
* `benchmarks/field-notes`: Initial 3 CC-BY-4.0 synthetic cross-market failure fixtures (`FN-001` split-rail finality divergence, `FN-002` Solana authority vs. SPL ATA mapping, `FN-003` OWASP ASI06 shared-origin illusion).
* Automated GitHub Actions CI running Node tests, Python pytest suite, contract compilation, and Gitleaks secret scanning on every push and pull request.
