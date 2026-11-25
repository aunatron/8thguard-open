import json

import httpx
import pytest
from eighthguard_networks import ERC3643_SELECTORS, ChainEvidence, inspect_erc3643

TOKEN = "0x" + "11" * 20
IDENTITY_REGISTRY = "0x" + "22" * 20
COMPLIANCE = "0x" + "33" * 20
ONCHAIN_ID = "0x" + "44" * 20
HOLDER = "0x" + "aa" * 20


def abi_word(value: int) -> str:
    return "0x" + f"{value:064x}"


def abi_address(addr: str) -> str:
    return "0x" + ("0" * 24) + addr[2:].lower()


async def run_inspect(network, token, handler, holder=None):
    def transport_handler(request):
        call = json.loads(request.content)
        outcome = handler(call)
        if isinstance(outcome, dict) and "error" in outcome:
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 1, "error": outcome["error"]}
            )
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": outcome}
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(transport_handler)
    ) as client:
        return await inspect_erc3643(
            ChainEvidence(client), network, token, holder_address=holder
        )


def healthy_erc3643_handler(chain_id_hex: str):
    def handle(call):
        method = call["method"]
        if method == "eth_chainId":
            return chain_id_hex
        if method == "eth_getCode":
            return "0x60806040"
        if method == "eth_call":
            tx = call["params"][0]
            to = tx["to"].lower()
            data = tx["data"].lower()
            if to == TOKEN:
                if data == ERC3643_SELECTORS["paused"]:
                    return abi_word(0)
                if data == ERC3643_SELECTORS["identityRegistry"]:
                    return abi_address(IDENTITY_REGISTRY)
                if data == ERC3643_SELECTORS["compliance"]:
                    return abi_address(COMPLIANCE)
                if data == ERC3643_SELECTORS["onchainID"]:
                    return abi_address(ONCHAIN_ID)
                if data.startswith(ERC3643_SELECTORS["isFrozen"]):
                    return abi_word(0)
                if data.startswith(ERC3643_SELECTORS["getFrozenTokens"]):
                    return abi_word(0)
            if to == IDENTITY_REGISTRY and data.startswith(
                ERC3643_SELECTORS["isVerified"]
            ):
                return abi_word(1)
        return {"error": {"code": -32000, "message": "execution reverted"}}

    return handle


@pytest.mark.parametrize(
    "network,chain_hex",
    [("base-mainnet", "0x2105"), ("celo-mainnet", "0xa4ec"), ("xdc-mainnet", "0x32")],
)
async def test_healthy_erc3643_token_and_verified_holder(network, chain_hex):
    res = await run_inspect(
        network, TOKEN, healthy_erc3643_handler(chain_hex), holder=HOLDER
    )
    assert res["status"] == "observed"
    assert res["erc3643_detected"] is True
    assert res["controls"] == {
        "paused": False,
        "identity_registry": IDENTITY_REGISTRY,
        "compliance_module": COMPLIANCE,
        "onchain_id": ONCHAIN_ID,
    }
    assert res["holder_checks"] == {
        "address": HOLDER,
        "is_frozen": False,
        "frozen_tokens_base_units": "0",
        "identity_verified": True,
    }
    assert res["risk_indicators"] == []
    assert res["unknowns"] == []
    assert len(res["limitations"]) >= 2


async def test_paused_frozen_and_unverified_holder_flags_all_indicators():
    base = healthy_erc3643_handler("0x2105")

    def handle(call):
        if call["method"] == "eth_call":
            to = call["params"][0]["to"].lower()
            data = call["params"][0]["data"].lower()
            if to == TOKEN and data == ERC3643_SELECTORS["paused"]:
                return abi_word(1)
            if to == TOKEN and data.startswith(ERC3643_SELECTORS["isFrozen"]):
                return abi_word(1)
            if to == TOKEN and data.startswith(ERC3643_SELECTORS["getFrozenTokens"]):
                return abi_word(500_000)
            if to == IDENTITY_REGISTRY and data.startswith(
                ERC3643_SELECTORS["isVerified"]
            ):
                return abi_word(0)
        return base(call)

    res = await run_inspect("base-mainnet", TOKEN, handle, holder=HOLDER)
    assert res["status"] == "observed"
    assert res["controls"]["paused"] is True
    assert res["holder_checks"]["is_frozen"] is True
    assert res["holder_checks"]["frozen_tokens_base_units"] == "500000"
    assert res["holder_checks"]["identity_verified"] is False
    assert set(res["risk_indicators"]) == {
        "token_paused",
        "holder_frozen",
        "partial_tokens_frozen",
        "holder_not_verified_in_identity_registry",
    }


async def test_plain_erc20_reverts_preserve_explicit_unknowns():
    def handle(call):
        if call["method"] == "eth_chainId":
            return "0x2105"
        if call["method"] == "eth_getCode":
            return "0x60806040"
        return {"error": {"code": -32000, "message": "execution reverted"}}

    res = await run_inspect("base-mainnet", TOKEN, handle, holder=HOLDER)
    assert res["status"] == "partial_or_non_erc3643"
    assert res["erc3643_detected"] is False
    assert "missing_erc3643_identity_registry" in res["risk_indicators"]
    assert "missing_erc3643_compliance_module" in res["risk_indicators"]
    assert "identity_registry_unavailable" in res["unknowns"]
    assert "holder_eligibility_unknown_no_identity_registry" in res["unknowns"]


async def test_wrong_chain_id_and_non_contract_fail_safely():
    wrong_chain = await run_inspect(
        "base-mainnet", TOKEN, healthy_erc3643_handler("0x1"), holder=HOLDER
    )
    assert wrong_chain["status"] == "unknown"
    assert "rpc_chain_id_mismatch" in wrong_chain["risk_indicators"]
    assert "network_identity_unverified" in wrong_chain["unknowns"]

    def eoa_handler(call):
        if call["method"] == "eth_chainId":
            return "0x2105"
        if call["method"] == "eth_getCode":
            return "0x"
        pytest.fail("should not invoke eth_call on an EOA")

    eoa = await run_inspect("base-mainnet", TOKEN, eoa_handler, holder=HOLDER)
    assert eoa["status"] == "not_a_contract"
    assert "target_has_no_contract_bytecode" in eoa["risk_indicators"]


async def test_dirty_abi_words_become_unknown_not_false():
    base = healthy_erc3643_handler("0x2105")

    def handle(call):
        if call["method"] == "eth_call":
            data = call["params"][0]["data"].lower()
            if data == ERC3643_SELECTORS["paused"]:
                return abi_word(2)  # invalid bool word
            if data == ERC3643_SELECTORS["identityRegistry"]:
                return "0x" + "ff" * 32  # dirty upper 12 bytes
        return base(call)

    res = await run_inspect("base-mainnet", TOKEN, handle)
    assert res["controls"]["paused"] is None
    assert res["controls"]["identity_registry"] is None
    assert "paused_unavailable" in res["unknowns"]
    assert "identity_registry_unavailable" in res["unknowns"]


async def test_rejects_non_evm_and_bad_address_before_rpc():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: pytest.fail("unexpected RPC"))
    ) as client:
        ev = ChainEvidence(client)
        with pytest.raises(ValueError):
            await inspect_erc3643(ev, "solana-mainnet", TOKEN)
        with pytest.raises(ValueError):
            await inspect_erc3643(ev, "base-mainnet", "0xnotanaddress")
