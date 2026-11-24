"""Small public, read-only source checks. Never submits a transaction."""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from eighthguard_networks import NETWORKS, ChainEvidence


async def main():
    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        source = ChainEvidence(client)

        async def check(network):
            async with semaphore:
                result = {
                    "network": network,
                    "checked_at": datetime.now(UTC).isoformat(),
                    "broadcast": False,
                }
                try:
                    async with asyncio.timeout(45):
                        identity = NETWORKS[network][1]
                        if isinstance(identity, int):
                            actual = await source.rpc(network, "eth_chainId", [])
                            result["identity_matches"] = int(actual, 16) == identity
                            block = await source.rpc(
                                network, "eth_getBlockByNumber", ["latest", False]
                            )
                            transactions = block.get("transactions", [])
                            for offset in range(1, 4):
                                if transactions:
                                    break
                                block = await source.rpc(
                                    network,
                                    "eth_getBlockByNumber",
                                    [hex(int(block["number"], 16) - offset), False],
                                )
                                transactions = block.get("transactions", [])
                            txid = transactions[0] if transactions else None
                        elif network.startswith("solana-"):
                            actual = await source.rpc(network, "getGenesisHash", [])
                            result["identity_matches"] = actual == identity
                            rows = await source.rpc(
                                network,
                                "getSignaturesForAddress",
                                [
                                    "11111111111111111111111111111111",
                                    {"limit": 1, "commitment": "confirmed"},
                                ],
                            )
                            txid = rows[0]["signature"] if rows else None
                        else:
                            actual = await source.rpc(network, "getNetwork", {})
                            result["identity_matches"] = (
                                actual.get("passphrase") == identity
                            )
                            horizon = (
                                "https://horizon-testnet.stellar.org"
                                if network.endswith("testnet")
                                else "https://horizon.stellar.org"
                            )
                            response = await client.get(
                                horizon + "/transactions",
                                params={"order": "desc", "limit": 1},
                            )
                            response.raise_for_status()
                            rows = response.json()["_embedded"]["records"]
                            txid = rows[0]["hash"] if rows else None
                        if txid:
                            result["observation"] = await source.observe(network, txid)
                        else:
                            result["status"] = "identity_checked_no_recent_transaction"
                except (
                    httpx.HTTPError,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                    TimeoutError,
                ):
                    result["status"] = "source_unavailable_or_response_unverified"
                return result

        networks = sys.argv[2:] or list(NETWORKS)
        if set(networks) - set(NETWORKS):
            raise ValueError("unknown network")
        results = await asyncio.gather(*(check(name) for name in networks))
    output = {
        "schema": "network-smoke.1",
        "kind": "public_read_only",
        "results": results,
    }
    Path(sys.argv[1]).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            [
                {
                    "network": r["network"],
                    "identity": r.get("identity_matches"),
                    "outcome": r.get("observation", {}).get("outcome"),
                    "status": r.get("status"),
                    "transfers": len(r.get("observation", {}).get("transfers", [])),
                }
                for r in results
            ]
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
