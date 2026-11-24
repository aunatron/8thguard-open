"""Bounded, read-only network observations. No signing, token issuance or fund movement."""

import asyncio
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from urllib.parse import urlsplit

import base58
import httpx

from .models import Network, validate_transaction

NETWORKS = {
    "xdc-apothem": ("https://rpc.apothem.network", 51),
    "xdc-mainnet": ("https://rpc.xinfin.network", 50),
    "ethereum-mainnet": ("https://ethereum-rpc.publicnode.com", 1),
    "base-mainnet": ("https://mainnet.base.org", 8453),
    "arbitrum-mainnet": ("https://arb1.arbitrum.io/rpc", 42161),
    "optimism-mainnet": ("https://mainnet.optimism.io", 10),
    "polygon-mainnet": ("https://polygon.drpc.org", 137),
    "avalanche-mainnet": ("https://api.avax.network/ext/bc/C/rpc", 43114),
    "celo-mainnet": ("https://forno.celo.org", 42220),
    "bnb-mainnet": ("https://bsc-dataseed.bnbchain.org", 56),
    "solana-devnet": (
        "https://api.devnet.solana.com",
        "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG",
    ),
    "solana-mainnet": (
        "https://api.mainnet-beta.solana.com",
        "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d",
    ),
    "stellar-testnet": (
        "https://soroban-testnet.stellar.org",
        "Test SDF Network ; September 2015",
    ),
    "stellar-mainnet": (
        "https://mainnet.sorobanrpc.com",
        "Public Global Stellar Network ; September 2015",
    ),
}
NATIVE_ASSETS = {
    51: "TXDC",
    50: "XDC",
    1: "ETH",
    8453: "ETH",
    42161: "ETH",
    10: "ETH",
    137: "POL",
    43114: "AVAX",
    42220: "CELO",
    56: "BNB",
}
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFmu4m3YhJXZ8WjDZ8jQZ",
}


class ObservationError(ValueError):
    pass


def quantity(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{1,64}", value):
        raise ObservationError("invalid integer")
    return int(value, 16)


def decimal_amount(atoms, decimals):
    if (
        isinstance(atoms, bool)
        or not isinstance(atoms, (int, str))
        or not re.fullmatch(r"[0-9]{1,78}", str(atoms))
    ):
        raise ObservationError("invalid base units")
    if type(decimals) is not int or not 0 <= decimals <= 36:
        raise ObservationError("unsupported precision")
    with localcontext() as context:
        context.prec = 120
        value = format(Decimal(str(atoms)) / (Decimal(10) ** decimals), "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def evm_address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ObservationError("invalid address")
    return value.lower()


def public_key(value):
    if (
        not isinstance(value, str)
        or not 32 <= len(value) <= 44
        or len(base58.b58decode(value)) != 32
    ):
        raise ObservationError("invalid account")
    return value


class ChainEvidence:
    def __init__(
        self, client: httpx.AsyncClient, endpoints=None, *, allow_loopback=False
    ):
        self.client, self.endpoints = client, endpoints or {}
        self.allow_loopback = allow_loopback
        if set(self.endpoints) - set(NETWORKS):
            raise ObservationError("unknown configured network")

    def endpoint(self, network):
        url = self.endpoints.get(network) or NETWORKS[network][0]
        parsed = urlsplit(url)
        local = False
        try:
            local = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            local = parsed.hostname == "localhost"
        if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
            raise ObservationError("invalid endpoint")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and local and self.allow_loopback
        ):
            raise ObservationError("secure endpoint required")
        # Endpoints are installation configuration, never request-body URLs.
        return url

    async def rpc(self, network, method, params=None):
        async with self.client.stream(
            "POST",
            self.endpoint(network),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params if params is not None else [],
            },
            timeout=8,
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise ObservationError("source unavailable")
            data = bytearray()
            async for part in response.aiter_bytes():
                data.extend(part)
                if len(data) > 2 * 1024 * 1024:
                    raise ObservationError("source response exceeds limit")
        try:
            result = json.loads(data)
        except (ValueError, RecursionError) as exc:
            raise ObservationError("source response not understood") from exc
        if (
            not isinstance(result, dict)
            or result.get("id") != 1
            or result.get("jsonrpc") != "2.0"
            or "error" in result
            or "result" not in result
        ):
            raise ObservationError("source response not understood")
        return result["result"]

    async def observe(self, network: Network, transaction_id: str):
        validate_transaction(network, transaction_id)
        now = datetime.now(UTC).isoformat()
        result = {
            "schema": "chain-observation.1",
            "network": network,
            "transaction_id": transaction_id,
            "observed_at": now,
            "source": {
                "kind": "json_rpc",
                "host": urlsplit(self.endpoint(network)).hostname,
            },
            "outcome": "unknown",
            "confirmation": "unknown",
            "coverage": "partial",
            "transfers": [],
            "unknowns": [],
            "network_identity": None,
        }
        try:
            async with asyncio.timeout(30):
                if isinstance(NETWORKS[network][1], int):
                    await self.evm(network, transaction_id, result)
                elif network.startswith("solana-"):
                    await self.solana(network, transaction_id, result)
                else:
                    await self.stellar(network, transaction_id, result)
        except (
            ObservationError,
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            AttributeError,
            TimeoutError,
        ):
            # No provider error bodies, URLs with keys or false failed/safe verdicts.
            result.update(
                outcome="unknown",
                confirmation="unknown",
                coverage="partial",
                transfers=[],
            )
            result["unknowns"].append(
                "The source was unavailable or its response could not be validated."
            )
        result["unknowns"] = sorted(set(result["unknowns"]))
        result["fingerprint"] = hashlib.sha256(
            json.dumps(
                result, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        return result

    async def evm(self, network, txid, out):
        if not re.fullmatch(r"0x[0-9a-fA-F]{64}", txid):
            raise ObservationError("invalid transaction identifier")
        chain = quantity(await self.rpc(network, "eth_chainId", []))
        if chain != NETWORKS[network][1]:
            raise ObservationError("wrong network")
        out["network_identity"] = str(chain)
        tx = await self.rpc(network, "eth_getTransactionByHash", [txid])
        receipt = await self.rpc(network, "eth_getTransactionReceipt", [txid])
        if not tx or not receipt:
            out["confirmation"] = "pending" if tx else "unknown"
            out["unknowns"].append(
                "A mined transaction and receipt were not both available."
            )
            return
        if (
            tx.get("hash", "").lower() != txid.lower()
            or receipt.get("transactionHash", "").lower() != txid.lower()
        ):
            raise ObservationError("transaction binding mismatch")
        number = quantity(receipt["blockNumber"])
        block = await self.rpc(
            network, "eth_getBlockByNumber", [receipt["blockNumber"], False]
        )
        if (
            not block
            or block["hash"].lower() != receipt["blockHash"].lower()
            or tx["blockHash"].lower() != block["hash"].lower()
            or quantity(block["number"]) != number
        ):
            raise ObservationError("noncanonical block")
        head = quantity(await self.rpc(network, "eth_blockNumber", []))
        out["block"] = {
            "number": number,
            "hash": block["hash"].lower(),
            "confirmations": max(0, head - number + 1),
        }
        out["confirmation"] = "confirmed" if head >= number else "unknown"
        try:
            finalized = await self.rpc(
                network, "eth_getBlockByNumber", ["finalized", False]
            )
            if finalized and quantity(finalized["number"]) >= number:
                out["confirmation"] = "finalized"
        except ObservationError:
            out["unknowns"].append(
                "The endpoint did not establish finalized-block coverage."
            )
        status = receipt.get("status")
        out["outcome"] = (
            "succeeded"
            if status == "0x1"
            else "failed"
            if status == "0x0"
            else "unknown"
        )
        if out["outcome"] != "succeeded":
            out["unknowns"].append(
                "A failed or unknown transaction does not establish a completed transfer."
            )
            return
        value = quantity(tx["value"])
        if value and tx.get("to"):
            out["transfers"].append(
                {
                    "kind": "native",
                    "source": evm_address(tx["from"]),
                    "recipient": evm_address(tx["to"]),
                    "asset": NATIVE_ASSETS[chain],
                    "amount": decimal_amount(value, 18),
                    "base_units": str(value),
                    "decimals": 18,
                }
            )
        logs = receipt.get("logs")
        if not isinstance(logs, list) or len(logs) > 200:
            raise ObservationError("unsupported log volume")
        for log in logs:
            topics = log.get("topics", [])
            if len(topics) != 3 or topics[0].lower() != TRANSFER_TOPIC:
                continue  # NFT transfers and other contract events are not ERC-20 evidence.
            if log.get("removed") or not all(
                re.fullmatch(r"0x[0-9a-fA-F]{64}", topic) for topic in topics
            ):
                raise ObservationError("invalid transfer log")
            if (
                log.get("transactionHash", "").lower() != txid.lower()
                or log.get("blockHash", "").lower() != block["hash"].lower()
            ):
                raise ObservationError("log binding mismatch")
            token, atoms = evm_address(log["address"]), quantity(log["data"])
            transfer = {
                "kind": "erc20",
                "source": evm_address("0x" + topics[1][-40:]),
                "recipient": evm_address("0x" + topics[2][-40:]),
                "asset": token,
                "base_units": str(atoms),
                "amount": None,
                "decimals": None,
                "log_index": quantity(log["logIndex"]),
            }
            try:
                decimals = quantity(
                    await self.rpc(
                        network,
                        "eth_call",
                        [{"to": token, "data": "0x313ce567"}, receipt["blockNumber"]],
                    )
                )
                transfer.update(
                    decimals=decimals, amount=decimal_amount(atoms, decimals)
                )
            except ObservationError:
                out["unknowns"].append(
                    "A token's historical decimals were unavailable; its amount remains base units only."
                )
            out["transfers"].append(transfer)
            if len(out["transfers"]) >= 20:
                out["unknowns"].append("Transfer decoding is limited to 20 entries.")
                break
        out["unknowns"].append(
            "Internal native transfers, token identity and arbitrary contract effects are not independently established."
        )
        out["coverage"] = (
            "supported_transfers" if tx.get("input", "0x") == "0x" else "partial"
        )

    async def solana(self, network, txid, out):
        if len(base58.b58decode(txid)) != 64:
            raise ObservationError("invalid signature")
        genesis = await self.rpc(network, "getGenesisHash", [])
        if genesis != NETWORKS[network][1]:
            raise ObservationError("wrong network")
        out["network_identity"] = genesis
        tx = await self.rpc(
            network,
            "getTransaction",
            [
                txid,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 1,
                },
            ],
        )
        status = await self.rpc(
            network,
            "getSignatureStatuses",
            [[txid], {"searchTransactionHistory": True}],
        )
        if not tx:
            out["unknowns"].append(
                "The transaction may be unconfirmed, outside source history or unknown."
            )
            return
        version = tx.get("version")
        if (
            not (version == "legacy" or (type(version) is int and version in (0, 1)))
            or txid not in tx["transaction"]["signatures"]
        ):
            raise ObservationError("transaction binding or version mismatch")
        meta = tx.get("meta")
        if not isinstance(meta, dict) or "err" not in meta:
            raise ObservationError("execution metadata unavailable")
        state = status["value"][0]
        if not state or state["slot"] != tx["slot"] or state.get("err") != meta["err"]:
            raise ObservationError("status binding mismatch")
        out["outcome"] = "succeeded" if meta["err"] is None else "failed"
        out["confirmation"] = (
            state.get("confirmationStatus")
            if state.get("confirmationStatus") in {"confirmed", "finalized"}
            else "unknown"
        )
        out["block"] = {"slot": tx["slot"]}
        if out["outcome"] != "succeeded":
            out["unknowns"].append(
                "Failed instructions are not reported as completed transfers."
            )
            return
        message = tx["transaction"]["message"]
        keys = [
            key["pubkey"] if isinstance(key, dict) else key
            for key in message["accountKeys"]
        ]
        balances = {}
        for balance in [
            *meta.get("preTokenBalances", []),
            *meta.get("postTokenBalances", []),
        ]:
            index = balance["accountIndex"]
            if type(index) is not int or not 0 <= index < len(keys):
                raise ObservationError("invalid token account index")
            balances[keys[index]] = balance
        instructions = [
            ("outer:" + str(i), item) for i, item in enumerate(message["instructions"])
        ]
        for inner in meta.get("innerInstructions", []):
            instructions.extend(
                (f"inner:{inner['index']}:{i}", item)
                for i, item in enumerate(inner["instructions"])
            )
        if len(instructions) > 300:
            raise ObservationError("unsupported instruction volume")
        for ref, instruction in instructions:
            parsed, program = instruction.get("parsed"), instruction.get("programId")
            if not isinstance(parsed, dict) or parsed.get("type") not in {
                "transfer",
                "transferChecked",
            }:
                out["unknowns"].append(
                    "Some instructions are outside supported transfer decoding."
                )
                continue
            info = parsed["info"]
            if program == SYSTEM_PROGRAM and parsed["type"] == "transfer":
                atoms = info["lamports"]
                out["transfers"].append(
                    {
                        "kind": "native",
                        "source": public_key(info["source"]),
                        "recipient": public_key(info["destination"]),
                        "asset": "SOL",
                        "base_units": str(atoms),
                        "amount": decimal_amount(atoms, 9),
                        "decimals": 9,
                        "instruction": ref,
                    }
                )
            elif program in TOKEN_PROGRAMS:
                if program == "TokenzQdBNbLqP5VEhdkAS6EPFmu4m3YhJXZ8WjDZ8jQZ":
                    out["unknowns"].append(
                        "Token-2022 amounts describe transfer instructions; fees, extensions and net received amounts are not established."
                    )
                source, recipient = (
                    public_key(info["source"]),
                    public_key(info["destination"]),
                )
                balance = balances.get(recipient) or balances.get(source)
                token_amount = info.get("tokenAmount")
                if not balance or (
                    parsed["type"] == "transferChecked"
                    and balance["mint"] != info.get("mint")
                ):
                    out["unknowns"].append(
                        "A token transfer's mint/decimals could not be bound to its accounts."
                    )
                    continue
                mint = public_key(balance["mint"])
                decimals = balance["uiTokenAmount"]["decimals"]
                atoms = token_amount["amount"] if token_amount else info["amount"]
                if token_amount and token_amount["decimals"] != decimals:
                    raise ObservationError("token precision conflict")
                owner = balances.get(recipient, {}).get("owner")
                out["transfers"].append(
                    {
                        "kind": "spl",
                        "source": source,
                        "recipient": recipient,
                        "recipient_kind": "token_account",
                        "owner_observed": public_key(owner) if owner else None,
                        "asset": "spl:" + mint,
                        "base_units": str(atoms),
                        "decimals": decimals,
                        "amount": decimal_amount(atoms, decimals),
                        "instruction": ref,
                    }
                )
            else:
                out["unknowns"].append(
                    "An instruction's program is not a supported transfer program."
                )
            if len(out["transfers"]) >= 50:
                out["unknowns"].append("Transfer decoding is limited to 50 entries.")
                break
        out["coverage"] = "partial" if out["unknowns"] else "supported_transfers"

    async def stellar(self, network, txid, out):
        from stellar_sdk import parse_transaction_envelope_from_xdr
        from stellar_sdk.operation import CreateAccount, Payment

        if not re.fullmatch(r"[a-fA-F0-9]{64}", txid):
            raise ObservationError("invalid transaction hash")
        identity = await self.rpc(network, "getNetwork", {})
        if identity.get("passphrase") != NETWORKS[network][1]:
            raise ObservationError("wrong network")
        out["network_identity"] = identity["passphrase"]
        tx = await self.rpc(network, "getTransaction", {"hash": txid.lower()})
        if tx.get("status") not in {"SUCCESS", "FAILED"}:
            out["unknowns"].append(
                "The transaction is not in this RPC source's retained history or is not yet confirmed."
            )
            return
        envelope = parse_transaction_envelope_from_xdr(
            tx["envelopeXdr"], identity["passphrase"]
        )
        if envelope.hash_hex().lower() != txid.lower():
            raise ObservationError("transaction binding mismatch")
        transaction = envelope.transaction
        if hasattr(transaction, "inner_transaction_envelope"):
            transaction = transaction.inner_transaction_envelope.transaction
        out["outcome"] = "succeeded" if tx["status"] == "SUCCESS" else "failed"
        out["confirmation"] = "finalized"
        out["block"] = {"ledger": tx["ledger"]}
        if out["outcome"] != "succeeded":
            out["unknowns"].append("Failed operations are not completed payments.")
            return
        for index, operation in enumerate(transaction.operations):
            sender = operation.source or transaction.source
            sender = getattr(sender, "account_muxed", None) or getattr(
                sender, "account_id", str(sender)
            )
            if isinstance(operation, Payment):
                asset = (
                    "XLM"
                    if operation.asset.is_native()
                    else operation.asset.code + ":" + operation.asset.issuer
                )
                destination = (
                    getattr(operation.destination, "account_muxed", None)
                    or operation.destination.account_id
                )
                out["transfers"].append(
                    {
                        "kind": "payment",
                        "source": sender,
                        "recipient": destination,
                        "asset": asset,
                        "amount": operation.amount,
                        "decimals": 7,
                        "base_units": str(int(Decimal(operation.amount) * 10000000)),
                        "operation": index,
                    }
                )
            elif isinstance(operation, CreateAccount):
                out["transfers"].append(
                    {
                        "kind": "create_account",
                        "source": sender,
                        "recipient": operation.destination,
                        "asset": "XLM",
                        "amount": operation.starting_balance,
                        "decimals": 7,
                        "base_units": str(
                            int(Decimal(operation.starting_balance) * 10000000)
                        ),
                        "operation": index,
                    }
                )
            else:
                out["unknowns"].append(
                    "Path payments, contract effects and other operation types require additional decoding."
                )
        out["coverage"] = "partial" if out["unknowns"] else "supported_transfers"
