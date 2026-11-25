# 8thGuard Open Verification Toolkit

Public extraction of **8thGuard**'s standalone verification packages, read-only multi-chain observation adapters, opaque commitment contract, and synthetic emerging-market benchmark Field Notes, built and actively maintained by **Aunatron Systems Limited**.

* **Website:** https://8thguard.com
* **Live Browser Verifier:** https://8thguard.com/verify#agent-receipts
* **Academy & Field Notes:** https://academy.8thguard.com/commons
* **Code License:** Apache License 2.0 (`LICENSE`)
* **Benchmark & Field Note Data License:** CC-BY-4.0 (`DATA_LICENSE`)

> **Operating Boundaries:** Everything in this repository is strictly read-only and non-custodial. No wallet connections, no private key custody, no escrow, no fund movement, and no personal data written onchain.

---

## Packages Included (`v0.1.1`)

| Path | License | What It Does |
| :--- | :--- | :--- |
| `packages/receipt-verifier` | `Apache-2.0` | Zero-dependency Node 24 / Web Crypto verifier for canonical JSON `Ed25519` Agent Evidence Receipts, keeping content integrity, expiry, live revocation, and coverage strictly separate. |
| `packages/network-evidence` | `Apache-2.0` | Bounded, read-only transaction observers across 14 network configurations (Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche C-Chain, Celo, BNB Chain, XDC Mainnet/Apothem, Solana Mainnet/Devnet, Stellar Mainnet/Testnet) with explicit unknowns, exact decimal strings, a read-only `ERC-3643` RWA preflight inspector (`inspect_erc3643` + `examples/erc3643_rwa_inspect.py`), and `examples/vet402_join_verify.py` for HTTP 402 settled-4xx reconciliation. |
| `contracts/evidence-registry` | `Apache-2.0` | Solidity `0.8.36` opaque SHA-256 receipt commitment and expiry registry with two-step ownership transfer and local Anvil tests. |
| `benchmarks/field-notes` | `CC-BY-4.0` | Synthetic, privacy-safe cross-market failure fixtures (split-rail finality divergence, Solana wallet authority vs. SPL ATA mapping, OWASP ASI06 shared-origin illusion, and ERC-3643 RWA freeze/eligibility gaps). |

---

## Quickstart (Runs 100% Offline in Under 2 Minutes)

No private API keys, database credentials, or live RPC tokens are required to run the full automated test suite.

### 1. Verify Ed25519 Agent Evidence Receipts (Node 24, Zero Dependencies)
```bash
cd packages/receipt-verifier
node --test verifier.test.mjs
```

### 2. Run Multi-Chain Observation Tests (Python 3.12, Mocked Offline Transport)
```bash
cd packages/network-evidence
python -m pip install -e ".[dev]"
pytest tests
```

### 3. Compile the Opaque Commitment Registry Contract (Node 24)
```bash
cd contracts/evidence-registry
npm ci --ignore-scripts
npm run compile
```
To run the full local EVM lifecycle test suite, start `npm run chain` in one terminal and run `npm test` in a second terminal.

---

## Digital Public Good Alignment & Do-No-Harm Design

* **SDG Alignment:** Supports **UN SDG 16** (accountable financial evidence and anti-fraud transparency), **SDG 9** (safe, interoperable digital public infrastructure), and **SDG 4** (open emerging-market verification literacy via synthetic Field Notes).
* **Platform Independence & Data Portability:** All verifiers, observers, and fixtures run 100% offline or against standard public JSON-RPC endpoints with zero proprietary cloud lock-in and standard JSON exports.
* **Privacy & Community Safeguards:** Zero personal data is stored or written onchain. Aunatron Systems Limited maintains active Data Controller registration under Ghana's Data Protection Act, 2012 (Act 843), verifiable via the [DPC Ghana Privacy Seal (`DPC-PSVS-2026-00207`)](https://app.dpc.gov.gh/s/DPC-PSVS-2026-00207). Community participation follows our [Code of Conduct](CODE_OF_CONDUCT.md) and [Security Policy](SECURITY.md).

---

## Commercial vs. Open Scope

This repository contains our independently usable open verification libraries, read-only chain adapters, commitment contract, and CC-BY-4.0 synthetic benchmark fixtures. Commercial SaaS applications, multi-tenant customer workspaces, billing, and Aunatron's proprietary collaborative orchestration software remain privately maintained.

We don't trust. We check.
