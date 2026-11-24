# Open Emerging-Market Benchmarks & Field Notes (`CC-BY-4.0`)

Synthetic, privacy-safe test fixtures documenting cross-market operational blind spots where autonomous AI agents and automated financial verification tools routinely misread partial or diverging evidence.

* **License:** Creative Commons Attribution 4.0 International (`../DATA_LICENSE`). Per CC-BY-4.0 Section 2(b)(2), no patent or trademark rights are licensed under this dataset license.
* **Privacy:** All fixtures contain strictly synthetic identifiers or publicly documented protocol patterns with zero personal or confidential customer data.

## Included Fixtures (`v0.1.0`)

1. `field-notes/FN-001-split-rail-finality.json`: Onchain transfer `TX-018` confirmed while downstream mobile-money payout `MP-217` remains pending (prevents premature merchant release or blind retry double-spends).
2. `field-notes/FN-002-solana-ata-vs-owner.json`: Cross-chain payer reconciliation difference between EVM `Transfer(from, to, value)` sender wallets and Solana SPL Associated Token Accounts (ATAs) vs. wallet authorities.
3. `field-notes/FN-003-shared-origin-illusion.json`: OWASP Agentic Top 10 (`ASI06` Context Poisoning) synthetic provenance graph where three seemingly independent reports collapse to one stale root source.
