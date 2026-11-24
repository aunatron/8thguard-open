#!/usr/bin/env python3
"""Reproducible join and verification script for vet402 x 8thGuard settled_4xx records.

Standard library only (Python 3.10+). No external packages required.

Usage:
  python3 vet402_join_verify.py \
    --export export.csv \
    --delivery delivery.csv \
    --records vet402_8thguard_joined.jsonl
"""

import argparse
import csv
import json
import sys


def load_csv_by_id(path: str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_declared_settled_4xx(export_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = [
        row
        for row in export_rows
        if row.get("held_reason") == "settled_4xx"
        and row.get("tx_hash", "").strip()
        and row.get("request_body") == "declared"
        and row.get("request_body_sha256", "").strip()
    ]
    selected.sort(key=lambda r: (r.get("attempted_at", ""), r.get("purchase_id", "")))
    return selected


def verify_records(
    export_rows: list[dict[str, str]],
    delivery_rows: list[dict[str, str]],
    joined_records: list[dict],
) -> int:
    expected = {r["purchase_id"]: r for r in select_declared_settled_4xx(export_rows)}
    delivery_by_id = {r["purchase_id"]: r for r in delivery_rows}
    by_id = {rec["external_reference"]: rec for rec in joined_records}

    missing_from_records = sorted(set(by_id) - set(expected))
    newly_added_in_export = sorted(set(expected) - set(by_id))

    errors: list[str] = []
    evm_payer_matches = 0
    solana_ata_notes = 0
    units_matches = 0
    nullable_body_bytes = 0

    for pid, rec in by_id.items():
        if rec.get("disposition") != "inconclusive_settled_4xx" or rec.get("seller_finding_issued") is not False:
            errors.append(f"{pid}: paid 4xx row must remain inconclusive with seller_finding_issued=False")

        exp = expected.get(pid)
        if not exp:
            continue
        dlv = delivery_by_id.get(pid)
        if not dlv:
            errors.append(f"{pid}: missing in delivery.csv")
            continue

        hx = rec["http_exchange"]
        meta = rec["vet402_settlement_meta"]
        obs = rec["chain_observation"]

        if exp.get("request_body") != "declared":
            errors.append(f"{pid}: request_body is {exp.get('request_body')!r}, expected 'declared'")
        if hx["request_body_sha256"] != exp["request_body_sha256"]:
            errors.append(f"{pid}: request_body_sha256 mismatch against export.csv")
        if hx["resource_key"] != exp["resource_key"]:
            errors.append(f"{pid}: resource_key mismatch against export.csv")
        if str(hx["http_status_paid"]) != exp["http_status_paid"]:
            errors.append(f"{pid}: http_status_paid mismatch against export.csv")
        if obs["transaction_id"].lower() != exp["tx_hash"].strip().lower():
            errors.append(f"{pid}: tx_hash mismatch against export.csv")

        raw_bb = dlv.get("body_bytes", "").strip()
        expected_bb = int(raw_bb) if raw_bb else None
        if expected_bb is None:
            nullable_body_bytes += 1
        if hx["response_body_bytes"] != expected_bb:
            errors.append(f"{pid}: response_body_bytes {hx['response_body_bytes']} != {expected_bb}")

        if obs["base_units"] == exp["confirmed_units"].strip():
            units_matches += 1
        else:
            errors.append(
                f"{pid}: onchain base_units {obs['base_units']} != confirmed_units {exp['confirmed_units']}"
            )

        dlv_payer = dlv.get("payer", "").strip()
        if meta["caip2_network"].startswith("eip155:"):
            if dlv_payer.lower() == (obs["source_wallet"] or "").lower():
                evm_payer_matches += 1
            else:
                errors.append(f"{pid}: EVM payer {dlv_payer} != onchain source {obs['source_wallet']}")
        elif meta["caip2_network"].startswith("solana:"):
            if dlv_payer != obs["source_wallet"]:
                solana_ata_notes += 1

    print(f"Joined records checked:           {len(by_id)}")
    print(f"Matching export.csv filter rows:  {len(expected)}")
    if newly_added_in_export:
        print(f"Newer export.csv rows since run:  {len(newly_added_in_export)}")
    if missing_from_records:
        print(f"Records no longer in 90d window:  {len(missing_from_records)}")
    print(f"Confirmed units == onchain units: {units_matches}/{len(by_id) - len(missing_from_records)}")
    print(f"EVM delivery payer == ERC20 from: {evm_payer_matches}")
    print(f"Solana owner vs SPL ATA rows:     {solana_ata_notes}")
    print(f"Rows with empty body_bytes:       {nullable_body_bytes}")
    print(f"Validation errors:                {len(errors)}")
    for err in errors[:20]:
        print(f"  ERROR: {err}", file=sys.stderr)
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify joined 8thGuard x vet402 settled_4xx records.")
    parser.add_argument("-e", "--export", required=True, help="Path to vet402 export.csv")
    parser.add_argument("-d", "--delivery", required=True, help="Path to vet402 delivery.csv")
    parser.add_argument("-r", "--records", required=True, help="Path to vet402_8thguard_joined.jsonl")
    args = parser.parse_args()

    export_rows = load_csv_by_id(args.export)
    delivery_rows = load_csv_by_id(args.delivery)
    with open(args.records, encoding="utf-8") as handle:
        joined_records = [json.loads(line) for line in handle if line.strip()]

    return verify_records(export_rows, delivery_rows, joined_records)


if __name__ == "__main__":
    raise SystemExit(main())
