// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Aunatron Systems Limited
pragma solidity 0.8.36;

/// @notice Opaque receipt commitments only. No assets, tokens, documents or execution rights.
contract EvidenceRegistry {
    enum Status { Missing, Active, Withdrawn, Superseded }
    struct Entry {
        bytes32 digest;
        address publisher;
        uint64 validUntil;
        uint64 anchoredAt;
        Status status;
        bytes32 supersededBy;
    }
    address public owner;
    address public proposedOwner;
    mapping(address => bool) public publishers;
    mapping(bytes32 => Entry) public entries;
    error Unauthorized();
    error InvalidCommitment();
    error InvalidState();
    error InvalidExpiry();
    event PublisherChanged(address indexed publisher, bool allowed);
    event OwnershipProposed(address indexed proposed);
    event OwnershipAccepted(address indexed previous, address indexed current);
    event Anchored(bytes32 indexed receiptRef, bytes32 digest, address indexed publisher, uint64 validUntil);
    event Withdrawn(bytes32 indexed receiptRef);
    event Superseded(bytes32 indexed receiptRef, bytes32 indexed replacement);

    constructor() {
        owner = msg.sender;
        publishers[msg.sender] = true;
        emit PublisherChanged(msg.sender, true);
    }
    modifier onlyOwner() { if (msg.sender != owner) revert Unauthorized(); _; }
    function setPublisher(address publisher, bool allowed) external onlyOwner {
        if (publisher == address(0)) revert InvalidCommitment();
        publishers[publisher] = allowed;
        emit PublisherChanged(publisher, allowed);
    }
    function proposeOwner(address next) external onlyOwner {
        if (next == address(0) || next == owner) revert InvalidCommitment();
        proposedOwner = next;
        emit OwnershipProposed(next);
    }
    function acceptOwnership() external {
        if (msg.sender != proposedOwner) revert Unauthorized();
        address previous = owner;
        owner = msg.sender;
        proposedOwner = address(0);
        emit OwnershipAccepted(previous, msg.sender);
    }
    function anchor(bytes32 receiptRef, bytes32 digest, uint64 validUntil) external {
        if (!publishers[msg.sender]) revert Unauthorized();
        if (receiptRef == bytes32(0) || digest == bytes32(0)) revert InvalidCommitment();
        Entry storage previous = entries[receiptRef];
        if (previous.status != Status.Missing) {
            if (previous.publisher == msg.sender && previous.digest == digest && previous.validUntil == validUntil && previous.status == Status.Active) return;
            revert InvalidState();
        }
        if (validUntil <= block.timestamp || validUntil > block.timestamp + 1 days) revert InvalidExpiry();
        entries[receiptRef] = Entry(digest, msg.sender, validUntil, uint64(block.timestamp), Status.Active, bytes32(0));
        emit Anchored(receiptRef, digest, msg.sender, validUntil);
    }
    function withdraw(bytes32 receiptRef) external {
        Entry storage entry = entries[receiptRef];
        if (entry.publisher != msg.sender) revert Unauthorized();
        if (entry.status == Status.Withdrawn) return;
        if (entry.status != Status.Active) revert InvalidState();
        entry.status = Status.Withdrawn;
        emit Withdrawn(receiptRef);
    }
    function supersede(bytes32 receiptRef, bytes32 replacement) external {
        Entry storage entry = entries[receiptRef];
        Entry storage next = entries[replacement];
        if (entry.publisher != msg.sender || next.publisher != msg.sender) revert Unauthorized();
        if (receiptRef == replacement || entry.status != Status.Active || next.status != Status.Active || next.validUntil <= block.timestamp) revert InvalidState();
        entry.status = Status.Superseded;
        entry.supersededBy = replacement;
        emit Superseded(receiptRef, replacement);
    }
}
