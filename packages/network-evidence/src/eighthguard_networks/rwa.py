"""Read-only ERC-3643 (T-REX) tokenised RWA preflight inspector.

Strictly read-only via eth_chainId, eth_getCode, and eth_call. Never holds private keys,
never submits transactions, and never treats missing onchain metadata as legal clearance.
"""

from datetime import UTC, datetime
import re
from typing import Any

import httpx

from .evidence import NETWORKS, ChainEvidence, ObservationError, evm_address, quantity
from .models import Network

ZERO_ADDRESS = "0x" + "00" * 20

# Exact 4-byte Keccak-256 function selectors for ERC-3643 (T-REX) read-only views.
ERC3643_SELECTORS = {
    "paused": "0x5c975abb",
    "identityRegistry": "0x134e18f4",
    "compliance": "0x6290865d",
    "onchainID": "0xaba63705",
    "isFrozen": "0xe5839836",
    "getFrozenTokens": "0x158b1a57",
    "isVerified": "0xb9209e33",
}


def _encode_address_call(selector: str, address: str) -> str:
    clean = evm_address(address)[2:]
    return f"{selector}{'0' * 24}{clean}"


def _decode_abi_bool(raw: Any) -> bool | None:
    if not isinstance(raw, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", raw):
        return None
    val = int(raw, 16)
    if val == 0:
        return False
    if val == 1:
        return True
    return None


def _decode_abi_address(raw: Any) -> str | None:
    if not isinstance(raw, str) or not re.fullmatch(r"0x0{24}[0-9a-fA-F]{40}", raw):
        return None
    return "0x" + raw[-40:].lower()


def _decode_abi_uint256_str(raw: Any) -> str | None:
    if not isinstance(raw, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", raw):
        return None
    return str(int(raw, 16))


async def _safe_eth_call(
    evidence: ChainEvidence, network: Network, target: str, data: str
) -> tuple[bool, Any]:
    try:
        res = await evidence.rpc(
            network, "eth_call", [{"to": target, "data": data}, "latest"]
        )
        return True, res
    except (ObservationError, httpx.HTTPError, ValueError, TypeError, TimeoutError):
        return False, None


async def inspect_erc3643(
    evidence: ChainEvidence,
    network: Network,
    token_address: str,
    holder_address: str | None = None,
) -> dict[str, Any]:
    """Inspect read-only ERC-3643 control and eligibility indicators on an EVM network."""
    if network not in NETWORKS or not isinstance(NETWORKS[network][1], int):
        raise ValueError("ERC-3643 inspection requires a configured EVM network")
    token = evm_address(token_address)
    holder = evm_address(holder_address) if holder_address is not None else None
    expected_chain_id = NETWORKS[network][1]
    checked_at = datetime.now(UTC).isoformat()

    base_limitations = [
        "Onchain ERC-3643 selectors do not establish off-chain issuer solvency, legal title, custody backing, or regulatory licensing.",
        "Read-only snapshot at latest block; token permissions and identity registries may change after inspection.",
    ]

    try:
        actual_chain_hex = await evidence.rpc(network, "eth_chainId", [])
        actual_chain_id = quantity(actual_chain_hex)
    except (ObservationError, httpx.HTTPError, ValueError, TypeError, TimeoutError):
        return {
            "schema": "erc3643-preflight.1",
            "network": network,
            "network_identity": str(expected_chain_id),
            "token": token,
            "holder": holder,
            "checked_at": checked_at,
            "status": "unknown",
            "erc3643_detected": False,
            "controls": {},
            "holder_checks": {},
            "risk_indicators": [],
            "unknowns": ["network_identity_unverified"],
            "limitations": base_limitations,
        }

    if actual_chain_id != expected_chain_id:
        return {
            "schema": "erc3643-preflight.1",
            "network": network,
            "network_identity": str(expected_chain_id),
            "token": token,
            "holder": holder,
            "checked_at": checked_at,
            "status": "unknown",
            "erc3643_detected": False,
            "controls": {},
            "holder_checks": {},
            "risk_indicators": ["rpc_chain_id_mismatch"],
            "unknowns": ["network_identity_unverified"],
            "limitations": base_limitations,
        }

    try:
        code = await evidence.rpc(network, "eth_getCode", [token, "latest"])
    except (ObservationError, httpx.HTTPError, ValueError, TypeError, TimeoutError):
        return {
            "schema": "erc3643-preflight.1",
            "network": network,
            "network_identity": str(expected_chain_id),
            "token": token,
            "holder": holder,
            "checked_at": checked_at,
            "status": "unknown",
            "erc3643_detected": False,
            "controls": {},
            "holder_checks": {},
            "risk_indicators": [],
            "unknowns": ["contract_bytecode_unverified"],
            "limitations": base_limitations,
        }

    if not isinstance(code, str) or code in ("0x", "0x0", ""):
        return {
            "schema": "erc3643-preflight.1",
            "network": network,
            "network_identity": str(expected_chain_id),
            "token": token,
            "holder": holder,
            "checked_at": checked_at,
            "status": "not_a_contract",
            "erc3643_detected": False,
            "controls": {},
            "holder_checks": {},
            "risk_indicators": ["target_has_no_contract_bytecode"],
            "unknowns": [],
            "limitations": base_limitations,
        }

    unknowns: list[str] = []
    risk_indicators: list[str] = []

    ok_paused, raw_paused = await _safe_eth_call(
        evidence, network, token, ERC3643_SELECTORS["paused"]
    )
    paused = _decode_abi_bool(raw_paused) if ok_paused else None
    if paused is None:
        unknowns.append("paused_unavailable")
    elif paused:
        risk_indicators.append("token_paused")

    ok_ir, raw_ir = await _safe_eth_call(
        evidence, network, token, ERC3643_SELECTORS["identityRegistry"]
    )
    identity_registry = _decode_abi_address(raw_ir) if ok_ir else None
    if identity_registry is None:
        unknowns.append("identity_registry_unavailable")
        risk_indicators.append("missing_erc3643_identity_registry")
    elif identity_registry == ZERO_ADDRESS:
        risk_indicators.append("zero_address_identity_registry")

    ok_comp, raw_comp = await _safe_eth_call(
        evidence, network, token, ERC3643_SELECTORS["compliance"]
    )
    compliance = _decode_abi_address(raw_comp) if ok_comp else None
    if compliance is None:
        unknowns.append("compliance_module_unavailable")
        risk_indicators.append("missing_erc3643_compliance_module")
    elif compliance == ZERO_ADDRESS:
        risk_indicators.append("zero_address_compliance_module")

    ok_oid, raw_oid = await _safe_eth_call(
        evidence, network, token, ERC3643_SELECTORS["onchainID"]
    )
    onchain_id = _decode_abi_address(raw_oid) if ok_oid else None
    if onchain_id is None:
        unknowns.append("onchain_id_unavailable")

    controls = {
        "paused": paused,
        "identity_registry": identity_registry,
        "compliance_module": compliance,
        "onchain_id": onchain_id,
    }

    erc3643_detected = (
        identity_registry is not None
        and identity_registry != ZERO_ADDRESS
        and compliance is not None
        and compliance != ZERO_ADDRESS
    )

    holder_checks: dict[str, Any] = {}
    if holder is not None:
        ok_frozen, raw_frozen = await _safe_eth_call(
            evidence,
            network,
            token,
            _encode_address_call(ERC3643_SELECTORS["isFrozen"], holder),
        )
        holder_frozen = _decode_abi_bool(raw_frozen) if ok_frozen else None
        if holder_frozen is None:
            unknowns.append("holder_freeze_status_unavailable")
        elif holder_frozen:
            risk_indicators.append("holder_frozen")

        ok_ftok, raw_ftok = await _safe_eth_call(
            evidence,
            network,
            token,
            _encode_address_call(ERC3643_SELECTORS["getFrozenTokens"], holder),
        )
        frozen_tokens = _decode_abi_uint256_str(raw_ftok) if ok_ftok else None
        if frozen_tokens is None:
            unknowns.append("holder_frozen_tokens_unavailable")
        elif int(frozen_tokens) > 0:
            risk_indicators.append("partial_tokens_frozen")

        holder_verified: bool | None = None
        if identity_registry and identity_registry != ZERO_ADDRESS:
            ok_ver, raw_ver = await _safe_eth_call(
                evidence,
                network,
                identity_registry,
                _encode_address_call(ERC3643_SELECTORS["isVerified"], holder),
            )
            holder_verified = _decode_abi_bool(raw_ver) if ok_ver else None
            if holder_verified is None:
                unknowns.append("holder_eligibility_unavailable")
            elif not holder_verified:
                risk_indicators.append("holder_not_verified_in_identity_registry")
        else:
            unknowns.append("holder_eligibility_unknown_no_identity_registry")

        holder_checks = {
            "address": holder,
            "is_frozen": holder_frozen,
            "frozen_tokens_base_units": frozen_tokens,
            "identity_verified": holder_verified,
        }

    status = "observed" if erc3643_detected and not unknowns else "partial_or_non_erc3643"

    return {
        "schema": "erc3643-preflight.1",
        "network": network,
        "network_identity": str(expected_chain_id),
        "token": token,
        "holder": holder,
        "checked_at": checked_at,
        "status": status,
        "erc3643_detected": erc3643_detected,
        "controls": controls,
        "holder_checks": holder_checks,
        "risk_indicators": risk_indicators,
        "unknowns": unknowns,
        "limitations": base_limitations,
    }
