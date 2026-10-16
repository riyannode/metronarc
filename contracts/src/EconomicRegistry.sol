// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Wallet commitments establish provenance, not independent verification of economic claims.
contract EconomicRegistry {
    uint256 public constant VERSION = 3;
    bytes32 private constant FACT_DOMAIN = sha256("METRON_FACT_ID_V3");
    bytes32 private constant RELATION_DOMAIN = sha256("METRON_RELATION_ID_V3");

    struct Fact {
        bytes32 factType;
        bytes32 schemaHash;
        bytes32 evidenceId;
        bytes32 contentHash;
        uint256 recordedAt;
    }

    struct Relationship {
        bytes32 relationType;
        bytes32 schemaHash;
        bytes32 fromFact;
        bytes32 toFact;
        bytes32 contentHash;
        uint256 recordedAt;
    }

    mapping(address => mapping(bytes32 => Fact)) public facts;
    mapping(address => mapping(bytes32 => Relationship)) public relationships;
    mapping(address => mapping(bytes32 => bytes32)) public evidenceFacts;

    error InvalidCommitment();
    error InvalidIdentity();
    error AlreadyRecorded();
    error EvidenceAlreadyUsed();
    error FactNotFound();

    event FactRecorded(
        address indexed wallet,
        bytes32 indexed factId,
        bytes32 indexed factType,
        bytes32 schemaHash,
        bytes32 evidenceId,
        bytes32 contentHash
    );
    event RelationshipRecorded(
        address indexed wallet,
        bytes32 indexed relationId,
        bytes32 indexed relationType,
        bytes32 schemaHash,
        bytes32 fromFact,
        bytes32 toFact,
        bytes32 contentHash
    );

    function recordFact(bytes32 factId, bytes32 factType, bytes32 schemaHash, bytes32 evidenceId, bytes32 contentHash)
        external
    {
        if (factType == bytes32(0) || schemaHash == bytes32(0) || evidenceId == bytes32(0) || contentHash == bytes32(0))
        {
            revert InvalidCommitment();
        }
        if (factId != sha256(abi.encode(FACT_DOMAIN, block.chainid, address(this), msg.sender, factType, evidenceId))) {
            revert InvalidIdentity();
        }
        if (facts[msg.sender][factId].contentHash != bytes32(0)) revert AlreadyRecorded();
        if (evidenceFacts[msg.sender][evidenceId] != bytes32(0)) revert EvidenceAlreadyUsed();
        facts[msg.sender][factId] = Fact(factType, schemaHash, evidenceId, contentHash, block.timestamp);
        evidenceFacts[msg.sender][evidenceId] = factId;
        emit FactRecorded(msg.sender, factId, factType, schemaHash, evidenceId, contentHash);
    }

    function recordRelationship(
        bytes32 relationId,
        bytes32 relationType,
        bytes32 schemaHash,
        bytes32 fromFact,
        bytes32 toFact,
        bytes32 contentHash
    ) external {
        if (relationType == bytes32(0) || schemaHash == bytes32(0) || contentHash == bytes32(0) || fromFact == toFact) revert InvalidCommitment();
        if (
            facts[msg.sender][fromFact].contentHash == bytes32(0) || facts[msg.sender][toFact].contentHash == bytes32(0)
        ) revert FactNotFound();
        if (
            relationId
                != sha256(
                    abi.encode(
                        RELATION_DOMAIN, block.chainid, address(this), msg.sender, relationType, fromFact, toFact
                    )
                )
        ) revert InvalidIdentity();
        if (relationships[msg.sender][relationId].contentHash != bytes32(0)) revert AlreadyRecorded();
        relationships[msg.sender][relationId] =
            Relationship(relationType, schemaHash, fromFact, toFact, contentHash, block.timestamp);
        emit RelationshipRecorded(msg.sender, relationId, relationType, schemaHash, fromFact, toFact, contentHash);
    }
}
