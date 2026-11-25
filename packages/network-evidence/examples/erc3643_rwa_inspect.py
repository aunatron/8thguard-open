"""Standalone read-only ERC-3643 (T-REX) RWA token preflight CLI example.

Usage:
  python examples/erc3643_rwa_inspect.py base-mainnet 0xTokenAddress [0xHolderAddress]

Never holds private keys, never submits transactions, and prints explicit unknowns.
"""

import asyncio
import json
import sys

import httpx
from eighthguard_networks import ChainEvidence, inspect_erc3643


async def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(
            "Usage: python examples/erc3643_rwa_inspect.py <evm-network> <token-address> [holder-address]",
            file=sys.stderr,
        )
        return 2
    network = sys.argv[1]
    token = sys.argv[2]
    holder = sys.argv[3] if len(sys.argv) == 4 else None
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        result = await inspect_erc3643(
            ChainEvidence(client), network, token, holder_address=holder
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
