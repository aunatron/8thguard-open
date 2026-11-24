# 8thGuard network evidence

Separately installable, bounded, read-only observations. No customer database, signing, wallet connection, custody, token issuance or transaction execution.

```python
import httpx
from eighthguard_networks import ChainEvidence

async with httpx.AsyncClient() as client:
    result = await ChainEvidence(client).observe("xdc-apothem", transaction_hash)
```

EVM readers cover XDC, Ethereum, Base, Arbitrum, Optimism, Polygon, Avalanche C-Chain, Celo and BNB Chain. Solana and Stellar use independent decoders. Names and exact identifiers are exported by `NETWORKS`; XDC, Solana and Stellar have test and mainnet configurations. An installation can override HTTPS endpoints. Request bodies cannot supply endpoints. HTTP loopback is explicit local test configuration only.

EVM: canonical block/transaction/receipt binding, outcome, native value and selected ERC-20 logs with historical decimals. NFTs, internal value traces and arbitrary contract effects are excluded. Rollup settlement and asset identity are not established by an EVM success flag. A source's finalized tag remains a reported source observation.

Solana: full pinned genesis hash, transaction signature, slot/error/confirmation agreement; parsed system and SPL/Token-2022 transfers for legacy/v0/v1 transactions. An SPL recipient is a token account; an observed owner is separate. Unparsed instructions and extension effects remain unknown.

Stellar: pinned network passphrase, SDK-parsed XDR and recomputed transaction hash, fee-bump envelopes, payment and account-creation operations with issuer-qualified assets. Path payments and Soroban effects remain partial. Provider history and testnet resets limit availability.

Amounts use exact decimal strings and base units. Failed transactions never establish completed transfers. Transport, oversized, rate-limited, malformed, unknown-version and wrong-network responses stay unknown. Each record names its host, observation time, scope, limitations and digest. A single RPC is a source, not independently verified consensus or a safety verdict.

Tests: `pytest tests` from `packages/network-evidence` after installing with `pip install -e ".[dev]"` (or `uv run --extra dev pytest tests`). Optional public reads: `python smoke.py OUTPUT.json [network ...]`. No broadcast occurs.

Sources checked 19 November 2026: [XDC](https://docs.xdc.network/learn/xdc-architecture/), [Solana RPC](https://solana.com/docs/rpc), [Solana genesis definitions](https://github.com/solana-labs/solana/blob/master/sdk/src/genesis_config.rs), [Stellar RPC providers](https://developers.stellar.org/docs/data/apis/rpc/providers), [Base](https://docs.base.org/get-started/connect-to-base), [Arbitrum](https://docs.arbitrum.io/chain-info), [Polygon](https://docs.polygon.technology/pos/reference/rpc-endpoints), [Avalanche](https://docs.avax.network/docs/primary-network), [BNB](https://docs.bnbchain.org/bnb-smart-chain/developers/wallet-configuration/). Public RPCs are rate limited; production provider selection is a separate operational decision.

Licensed under the Apache License, Version 2.0. See `LICENSE` in the repository root.
