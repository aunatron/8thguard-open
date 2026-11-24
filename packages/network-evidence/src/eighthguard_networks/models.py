import re
from typing import Literal

import base58

Network = Literal[
    "xdc-apothem",
    "xdc-mainnet",
    "ethereum-mainnet",
    "base-mainnet",
    "arbitrum-mainnet",
    "optimism-mainnet",
    "polygon-mainnet",
    "avalanche-mainnet",
    "celo-mainnet",
    "bnb-mainnet",
    "solana-devnet",
    "solana-mainnet",
    "stellar-testnet",
    "stellar-mainnet",
]


def validate_transaction(network: Network, value: str) -> str:
    if network.startswith("solana-"):
        try:
            valid = 64 <= len(value) <= 88 and len(base58.b58decode(value)) == 64
        except ValueError:
            valid = False
    else:
        valid = bool(
            re.fullmatch(
                r"[a-fA-F0-9]{64}"
                if network.startswith("stellar-")
                else r"0x[a-fA-F0-9]{64}",
                value,
            )
        )
    if not valid:
        raise ValueError("invalid transaction identifier for network")
    return value
