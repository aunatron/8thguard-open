# Changelog

All notable changes to the 8thGuard Open Verification Toolkit are documented here.

## [0.1.0] - 2026-11-24

### Added
* Initial standalone public release extracted cleanly for independent verification and open-source maintenance.
* `packages/receipt-verifier`: Zero-dependency Node 24 / Web Crypto Ed25519 canonical JSON verifier (`cli.mjs`, `index.mjs`) with tamper, expiry, and unknown offline lifecycle tests.
* `packages/network-evidence`: Bounded read-only transaction observation adapters covering 14 EVM, Solana, and Stellar network configurations with offline unit tests and the standalone `examples/vet402_join_verify.py` HTTP 402 settled-4xx verification script.
* `contracts/evidence-registry`: Solidity `0.8.36` opaque SHA-256 commitment and expiry registry under Apache-2.0 with reproducible compilation scripts and Anvil lifecycle tests.
* `benchmarks/field-notes`: Initial 3 CC-BY-4.0 synthetic cross-market failure fixtures (`FN-001` split-rail finality divergence, `FN-002` Solana authority vs. SPL ATA mapping, `FN-003` OWASP ASI06 shared-origin illusion).
* Automated GitHub Actions CI running Node tests, Python pytest suite, contract compilation, and Gitleaks secret scanning on every push and pull request.
