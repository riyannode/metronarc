// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Immutable, caller-namespaced commitments to locally reconciled economic activity.
contract EconomicRegistry {
    string public constant VERSION = "2";

    struct SpendRecord {
        address operatingWallet;
        bytes32 goalHash;
        bytes32 spendIntentHash;
        bytes32 paymentEvidenceHash;
        uint256 amount;
        uint256 recordedAt;
        uint256 revenueCount;
    }

    struct RevenueRecord {
        bytes32 spendId;
        bytes32 revenueEvidenceHash;
        uint256 revenueAmount;
        uint256 earnedCapital;
        uint256 recordedAt;
    }

    error InvalidSpendRecord();
    error SpendAlreadyRecorded(address operatingWallet, bytes32 spendId);
    error SpendNotFound(address operatingWallet, bytes32 spendId);
    error RevenueAlreadyRecorded(address operatingWallet, bytes32 revenueEvidenceHash);
    error InvalidRevenueRecord();

    mapping(address => mapping(bytes32 => SpendRecord)) public spendRecords;
    mapping(address => mapping(bytes32 => mapping(bytes32 => RevenueRecord))) public revenueRecords;
    mapping(address => mapping(bytes32 => bool)) public usedRevenueEvidence;

    event SpendRecorded(
        address indexed operatingWallet,
        bytes32 indexed spendId,
        bytes32 goalHash,
        bytes32 spendIntentHash,
        bytes32 paymentEvidenceHash,
        uint256 amount,
        uint256 recordedAt
    );
    event RevenueRecorded(
        address indexed operatingWallet,
        bytes32 indexed spendId,
        bytes32 indexed revenueEvidenceHash,
        uint256 revenueAmount,
        uint256 earnedCapital,
        uint256 recordedAt
    );

    function recordSpend(
        bytes32 spendId,
        bytes32 goalHash,
        bytes32 spendIntentHash,
        bytes32 paymentEvidenceHash,
        uint256 amount
    ) external {
        if (
            msg.sender == address(0) || spendId == bytes32(0) || goalHash == bytes32(0) || spendIntentHash == bytes32(0)
                || paymentEvidenceHash == bytes32(0) || amount == 0
        ) revert InvalidSpendRecord();
        if (spendRecords[msg.sender][spendId].operatingWallet != address(0)) {
            revert SpendAlreadyRecorded(msg.sender, spendId);
        }

        uint256 timestamp = block.timestamp;
        spendRecords[msg.sender][spendId] =
            SpendRecord(msg.sender, goalHash, spendIntentHash, paymentEvidenceHash, amount, timestamp, 0);
        emit SpendRecorded(msg.sender, spendId, goalHash, spendIntentHash, paymentEvidenceHash, amount, timestamp);
    }

    function recordRevenue(bytes32 spendId, bytes32 revenueEvidenceHash, uint256 revenueAmount, uint256 earnedCapital)
        external
    {
        SpendRecord storage spend = spendRecords[msg.sender][spendId];
        if (spend.operatingWallet == address(0)) revert SpendNotFound(msg.sender, spendId);
        if (revenueEvidenceHash == bytes32(0) || revenueAmount == 0 || earnedCapital > revenueAmount) {
            revert InvalidRevenueRecord();
        }
        if (usedRevenueEvidence[msg.sender][revenueEvidenceHash]) {
            revert RevenueAlreadyRecorded(msg.sender, revenueEvidenceHash);
        }

        uint256 timestamp = block.timestamp;
        usedRevenueEvidence[msg.sender][revenueEvidenceHash] = true;
        spend.revenueCount += 1;
        revenueRecords[msg.sender][spendId][revenueEvidenceHash] =
            RevenueRecord(spendId, revenueEvidenceHash, revenueAmount, earnedCapital, timestamp);
        emit RevenueRecorded(msg.sender, spendId, revenueEvidenceHash, revenueAmount, earnedCapital, timestamp);
    }
}
