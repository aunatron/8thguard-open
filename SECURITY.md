# Security Policy

Aunatron Systems Limited treats verification integrity and responsible security disclosure seriously.

## Scope

This policy covers the open-source packages in `github.com/aunatron/8thguard-open`:
* `packages/receipt-verifier`
* `packages/network-evidence`
* `contracts/evidence-registry`
* `benchmarks/`

## Reporting a Vulnerability

Please report suspected vulnerabilities privately by emailing **kev@aunatron.com** with:
1. The affected package, file path, and version/commit hash.
2. A clear reproduction case or synthetic proof of concept.
3. Any suggested mitigation or edge-case notes.

Please do not open public GitHub issues for unpatched cryptographic, signature-verification, or contract-logic vulnerabilities. We aim to acknowledge reports within 48 hours and coordinate a clean fix and public changelog note.

## Strict Safety Boundaries

* Never submit real private keys, live customer records, or personally identifiable information in issues, pull requests, or benchmarks.
* All test fixtures and Field Notes in `benchmarks/` must be strictly synthetic or publicly verifiable without private user data.
