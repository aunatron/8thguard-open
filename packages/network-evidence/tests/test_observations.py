import json

import base58
import httpx
import pytest
from eighthguard_networks import NETWORKS, ChainEvidence
from eighthguard_networks.evidence import NATIVE_ASSETS, TRANSFER_TOPIC, decimal_amount
from stellar_sdk import Account, Asset, Keypair, Network, TransactionBuilder

TX = "0x" + "11" * 32
BLOCK = "0x" + "22" * 32
SENDER = "0x" + "01" * 20
DEST = "0x" + "02" * 20
TOKEN = "0x" + "03" * 20


async def observed(network, txid, values, *, status=200):
    def handle(request):
        call = json.loads(request.content)
        result = values(call) if callable(values) else values[call["method"]]
        return httpx.Response(
            status, json={"jsonrpc": "2.0", "id": 1, "result": result}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        return await ChainEvidence(client).observe(network, txid)


def xdc_values():
    return {
        "eth_chainId": "0x33",
        "eth_getTransactionByHash": {
            "hash": TX,
            "blockHash": BLOCK,
            "value": hex(2 * 10**18),
            "from": SENDER,
            "to": DEST,
            "input": "0x",
        },
        "eth_getTransactionReceipt": {
            "transactionHash": TX,
            "blockNumber": "0x10",
            "blockHash": BLOCK,
            "status": "0x1",
            "logs": [],
        },
        "eth_getBlockByNumber": {"hash": BLOCK, "number": "0x20"},
        "eth_blockNumber": "0x20",
    }


def xdc_handler(values):
    def handle(call):
        if (
            call["method"] == "eth_getBlockByNumber"
            and call["params"][0] != "finalized"
        ):
            return {"hash": BLOCK, "number": "0x10"}
        return values[call["method"]]

    return handle


@pytest.mark.parametrize(
    "network,identity",
    [(name, value[1]) for name, value in NETWORKS.items() if isinstance(value[1], int)],
)
async def test_each_evm_network_pins_identity_and_uses_its_native_asset(
    network, identity
):
    values = xdc_values()
    values["eth_chainId"] = hex(identity)
    result = await observed(network, TX, xdc_handler(values))
    assert result["network_identity"] == str(identity)
    assert result["transfers"][0]["asset"] == NATIVE_ASSETS[identity]
    values["eth_chainId"] = hex(identity + 1)
    assert (await observed(network, TX, xdc_handler(values)))["outcome"] == "unknown"


@pytest.mark.parametrize(
    "network,identifier",
    [
        ("xdc-apothem", "0x123"),
        ("solana-devnet", "not-a-signature"),
        ("stellar-testnet", "0x" + "ab" * 32),
    ],
)
async def test_identifier_validation_precedes_any_request(network, identifier):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: pytest.fail("invalid identifier contacted source")
        )
    ) as client:
        with pytest.raises(ValueError):
            await ChainEvidence(client).observe(network, identifier)


async def test_xdc_native_canonical_transaction_and_wrong_chain():
    values = xdc_values()
    result = await observed("xdc-apothem", TX, xdc_handler(values))
    assert result["outcome"] == "succeeded" and result["confirmation"] == "finalized"
    assert result["transfers"][0] == {
        "kind": "native",
        "source": SENDER,
        "recipient": DEST,
        "asset": "TXDC",
        "amount": "2",
        "base_units": str(2 * 10**18),
        "decimals": 18,
    }
    values["eth_chainId"] = "0x1"
    wrong = await observed("xdc-apothem", TX, xdc_handler(values))
    assert wrong["outcome"] == "unknown" and wrong["transfers"] == []


async def test_failed_and_pending_xdc_never_report_completed_transfer():
    values = xdc_values()
    values["eth_getTransactionReceipt"]["status"] = "0x0"
    failure = await observed("xdc-apothem", TX, xdc_handler(values))
    assert failure["outcome"] == "failed" and not failure["transfers"]
    values["eth_getTransactionReceipt"] = None
    pending = await observed("xdc-apothem", TX, xdc_handler(values))
    assert pending["outcome"] == "unknown" and pending["confirmation"] == "pending"


async def test_erc20_historical_decimals_and_base_units():
    values = xdc_values()
    values["eth_getTransactionByHash"]["value"] = "0x0"
    values["eth_getTransactionByHash"]["input"] = "0xa9059cbb"
    values["eth_getTransactionReceipt"]["logs"] = [
        {
            "address": TOKEN,
            "topics": [
                TRANSFER_TOPIC,
                "0x" + "00" * 12 + SENDER[2:],
                "0x" + "00" * 12 + DEST[2:],
            ],
            "data": "0x" + f"{1500000:064x}",
            "logIndex": "0x0",
            "transactionHash": TX,
            "blockHash": BLOCK,
            "removed": False,
        }
    ]
    values["eth_call"] = "0x" + f"{6:064x}"
    calls = []

    def handler(call):
        calls.append(call)
        return xdc_handler(values)(call)

    result = await observed("xdc-apothem", TX, handler)
    assert result["transfers"][0]["amount"] == "1.5"
    assert next(c for c in calls if c["method"] == "eth_call")["params"][1] == "0x10"
    values["eth_call"] = "0xff"
    result = await observed("xdc-apothem", TX, xdc_handler(values))
    assert result["transfers"][0]["amount"] is None
    assert result["transfers"][0]["base_units"] == "1500000"


async def test_reorg_and_mismatched_receipt_fail_closed():
    values = xdc_values()
    values["eth_getTransactionByHash"]["blockHash"] = "0x" + "ff" * 32
    result = await observed("xdc-apothem", TX, xdc_handler(values))
    assert result["outcome"] == "unknown" and not result["transfers"]


def solana_values():
    sig = base58.b58encode(b"s" * 64).decode()
    source, dest = [base58.b58encode(bytes([i]) * 32).decode() for i in (1, 2)]
    values = {
        "getGenesisHash": NETWORKS["solana-devnet"][1],
        "getTransaction": {
            "version": 0,
            "slot": 42,
            "meta": {"err": None},
            "transaction": {
                "signatures": [sig],
                "message": {
                    "accountKeys": [source, dest],
                    "instructions": [
                        {
                            "programId": "11111111111111111111111111111111",
                            "parsed": {
                                "type": "transfer",
                                "info": {
                                    "source": source,
                                    "destination": dest,
                                    "lamports": 1500000000,
                                },
                            },
                        }
                    ],
                },
            },
        },
        "getSignatureStatuses": {
            "context": {"slot": 50},
            "value": [{"slot": 42, "err": None, "confirmationStatus": "finalized"}],
        },
    }
    return sig, values


@pytest.mark.parametrize("version", ["legacy", 0, 1])
async def test_solana_versions_and_explicit_confirmation(version):
    sig, values = solana_values()
    values["getTransaction"]["version"] = version
    calls = []

    def handler(call):
        calls.append(call)
        return values[call["method"]]

    result = await observed("solana-devnet", sig, handler)
    assert result["outcome"] == "succeeded" and result["confirmation"] == "finalized"
    assert result["transfers"][0]["amount"] == "1.5"
    call = next(c for c in calls if c["method"] == "getTransaction")
    assert call["params"][1]["maxSupportedTransactionVersion"] == 1


@pytest.mark.parametrize("version", [2, True, None, "1"])
async def test_unsupported_solana_versions_remain_unknown(version):
    sig, values = solana_values()
    values["getTransaction"]["version"] = version
    result = await observed("solana-devnet", sig, values)
    assert result["outcome"] == "unknown" and not result["transfers"]


async def test_solana_failed_unknown_and_wrong_status_binding():
    sig, values = solana_values()
    values["getTransaction"]["meta"]["err"] = {
        "InstructionError": [0, "InvalidArgument"]
    }
    values["getSignatureStatuses"]["value"][0]["err"] = values["getTransaction"][
        "meta"
    ]["err"]
    failure = await observed("solana-devnet", sig, values)
    assert failure["outcome"] == "failed" and not failure["transfers"]
    values["getSignatureStatuses"]["value"][0]["slot"] = 41
    result = await observed("solana-devnet", sig, values)
    assert result["outcome"] == "unknown"
    values["getTransaction"] = None
    result = await observed("solana-devnet", sig, values)
    assert result["outcome"] == "unknown" and result["unknowns"]


@pytest.mark.parametrize("fee_bump", [False, True])
async def test_stellar_envelope_payment_binding_and_issuer(fee_bump):
    sender, recipient, issuer = [
        Keypair.from_raw_ed25519_seed(bytes([i]) * 32) for i in (1, 2, 3)
    ]
    envelope = (
        TransactionBuilder(
            Account(sender.public_key, 1), Network.TESTNET_NETWORK_PASSPHRASE, 100
        )
        .append_payment_op(recipient.public_key, Asset("USD", issuer.public_key), "2.5")
        .set_timeout(300)
        .build()
    )
    envelope.sign(sender)
    if fee_bump:
        envelope = TransactionBuilder.build_fee_bump_transaction(
            sender.public_key, 100, envelope, Network.TESTNET_NETWORK_PASSPHRASE
        )
        envelope.sign(sender)
    txid = envelope.hash_hex()
    values = {
        "getNetwork": {"passphrase": Network.TESTNET_NETWORK_PASSPHRASE},
        "getTransaction": {
            "status": "SUCCESS",
            "ledger": 52,
            "envelopeXdr": envelope.to_xdr(),
        },
    }
    result = await observed("stellar-testnet", txid, values)
    assert result["outcome"] == "succeeded" and result["confirmation"] == "finalized"
    assert result["transfers"][0]["asset"] == "USD:" + issuer.public_key
    assert result["transfers"][0]["recipient"] == recipient.public_key
    assert result["transfers"][0]["amount"] == "2.5"
    mismatch = await observed("stellar-testnet", "ff" * 32, values)
    assert mismatch["outcome"] == "unknown"
    values["getTransaction"]["status"] = "FAILED"
    failure = await observed("stellar-testnet", txid, values)
    assert failure["outcome"] == "failed" and not failure["transfers"]


@pytest.mark.parametrize(
    "program",
    [
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "TokenzQdBNbLqP5VEhdkAS6EPFmu4m3YhJXZ8WjDZ8jQZ",
    ],
)
async def test_spl_recipient_is_token_account_and_extensions_stay_partial(program):
    sig, values = solana_values()
    tx = values["getTransaction"]
    source, destination = tx["transaction"]["message"]["accountKeys"]
    mint, owner = [base58.b58encode(bytes([i]) * 32).decode() for i in (3, 4)]
    tx["meta"]["postTokenBalances"] = [
        {
            "accountIndex": 1,
            "mint": mint,
            "owner": owner,
            "uiTokenAmount": {"decimals": 6},
        }
    ]
    tx["transaction"]["message"]["instructions"] = [
        {
            "programId": program,
            "parsed": {
                "type": "transferChecked",
                "info": {
                    "source": source,
                    "destination": destination,
                    "mint": mint,
                    "tokenAmount": {"amount": "1500000", "decimals": 6},
                },
            },
        }
    ]
    result = await observed("solana-devnet", sig, values)
    transfer = result["transfers"][0]
    assert (
        transfer["recipient"] == destination
        and transfer["recipient_kind"] == "token_account"
    )
    assert transfer["owner_observed"] == owner and transfer["amount"] == "1.5"
    if program.startswith("Tokenz"):
        assert result["coverage"] == "partial" and any(
            "net received" in item for item in result["unknowns"]
        )


async def test_stellar_account_creation_is_a_native_transfer():
    sender, recipient = [Keypair.from_raw_ed25519_seed(bytes([i]) * 32) for i in (1, 2)]
    envelope = (
        TransactionBuilder(
            Account(sender.public_key, 1), Network.TESTNET_NETWORK_PASSPHRASE, 100
        )
        .append_create_account_op(recipient.public_key, "2.5")
        .set_timeout(300)
        .build()
    )
    values = {
        "getNetwork": {"passphrase": Network.TESTNET_NETWORK_PASSPHRASE},
        "getTransaction": {
            "status": "SUCCESS",
            "ledger": 53,
            "envelopeXdr": envelope.to_xdr(),
        },
    }
    result = await observed("stellar-testnet", envelope.hash_hex(), values)
    assert (
        result["transfers"][0]["kind"] == "create_account"
        and result["transfers"][0]["asset"] == "XLM"
    )


async def test_unavailable_sources_never_become_success():
    result = await observed("xdc-apothem", TX, {}, status=429)
    assert result["outcome"] == "unknown" and result["confirmation"] == "unknown"
    assert not result["transfers"]


def test_integer_precision_without_float_rounding():
    assert (
        decimal_amount("123456789012345678901234567890", 18)
        == "123456789012.34567890123456789"
    )
    with pytest.raises(ValueError):
        decimal_amount(True, 6)
