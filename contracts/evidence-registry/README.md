# Evidence Registry pilot

Opaque receipt references, SHA-256 envelope commitments and expiry on XDC Apothem (chain `51`, default), Celo Mainnet (chain `42220`), and Base Mainnet (chain `8453`, with optional ERC-8021 Builder Code data suffix attribution). No token, funds, customer documents, transfer permission or execution. Compiler 0.8.36, optimizer 200, Paris EVM. `npm ci --ignore-scripts`, `npm run compile`, `npm run chain`, then `npm test` in a separate terminal (or `npm run test:celo` / `npm run test:base` for the self-contained local Celo `42220` and Base `8453` simulations). Tests use publicly known development keys that must never be reused on public networks.

Owner manages allowed publishers with a two-step owner transfer. An initial commitment is immutable; identical active anchor retries and repeated withdrawal are safe. Superseding requires a different active, unexpired replacement owned by the same publisher. Expiry is at most one day when initially anchored. Read both status and expiry; an `Active` enum alone does not establish a current receipt. Service withdrawal does not automatically change a blockchain entry.

Prepare without a wallet or broadcast:

```
node scripts/operator.mjs prepare --network celo-mainnet --operation deploy --out deployment-plan.json
node scripts/operator.mjs prepare --network base-mainnet --operation deploy --builder-code bc_YOURCODE --out base-deployment-plan.json
node scripts/operator.mjs prepare --network xdc-apothem --operation anchor --registry 0xREGISTRY --receipt receipt.json --trust pinned-keys.json --out anchor-plan.json
```

Plans are reviewable JSON with explicit network and chain ID (`51` for `xdc-apothem`, `42220` for `celo-mainnet`, `8453` for `base-mainnet`), exact bytecode/calldata (plus optional ERC-8021 Schema 0 attribution suffix), zero value, source and runtime fingerprints. For `withdraw`, use the original receipt; for `supersede`, also supply `--replacement replacement.json`. Source receipts remain private. Only opaque references and commitments go on chain. Independently check current service lifecycle before an operator transaction.

An explicitly authorised operator can set `REGISTRY_OPERATOR_PRIVATE_KEY` in the current process and run `node scripts/operator.mjs broadcast --broadcast --plan deployment-plan.json --out deployment-manifest.json`. The tool requires an allowlisted network (`xdc-apothem`, `celo-mainnet`, or `base-mainnet`) and HTTPS, verifies exact runtime, operation and publisher and reports the transaction reference before polling. For reproducible zero-PII synthetic benchmark anchor runs (hashing public Field Notes `FN-001`, `FN-002`, and `FN-004`), inspect dry-run plans with `node scripts/celo-demo-deploy.mjs` or `node scripts/base-demo-deploy.mjs --builder-code bc_YOURCODE` before running with `--broadcast --out <manifest>.json`. `--local-test --rpc http://127.0.0.1:8549` is restricted to dedicated loopback simulations. No browser or engine key is substituted. Never put operator keys in web settings, arguments, source files or output logs. Remove the process variable after use.

The private engine only reconciles supplied transaction hashes. Pin registry address, publisher and exact runtime SHA-256. It checks canonical transaction binding, the Anchored event, envelope hash, opaque reference, expiry and current contract state. Confirmation is explicitly RPC finalized or 12 canonical blocks; depth is not a promise of protocol finality. Recheck after reorganisation, lifecycle changes or provider failure. A failed or unknown check does not prove absence.

`artifacts/standard-input.json` and the source digest support reproducible compilation. Licensed under the Apache License, Version 2.0 (see `LICENSE` in the repository root). This pilot contract anchors opaque receipt commitments only; no formal external security audit certification is implied by these open artifacts.
