# Agent Evidence Receipt verifier

Node 24, no external runtime dependencies. `node cli.mjs receipt.json independently-pinned-keys.json` verifies the Python engine's Ed25519 envelope and emits its SHA-256 commitment. Trust input maps key identifiers to raw 32-byte public keys encoded as unpadded base64url. Obtain keys through an independently trusted channel; never trust a key merely because it accompanies a receipt.

The domain is `8thGuard Agent Evidence Receipt v1` followed by one zero byte. Signed bytes are UTF-8 canonical JSON of `{protected,body}`. Object keys are sorted; no whitespace, non-integer numbers, unsafe integers or unsupported values are accepted. Receipt field names are ASCII. The schema uses exact decimal strings for amounts. The envelope commitment hashes canonical JSON of the entire envelope, including the signature.

Content integrity, publisher trust, expiry, live service lifecycle, registry lifecycle and evidence coverage are separate. Offline verification always returns `current_status: unknown` and cannot establish that a receipt has not been withdrawn or superseded. An authentic expired receipt can retain historical integrity while being unusable as a current record. Neither authenticity nor a blockchain commitment establishes authority, ownership or safety.

`node --test verifier.test.mjs` checks tampering, independently pinned trust, expiry and unknown offline lifecycle. The local browser demonstration also exports a Python-signed receipt and verifies it with this utility before anchoring.

Licensed under the Apache License, Version 2.0. See `LICENSE` in the repository root.
