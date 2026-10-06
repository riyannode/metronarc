// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {EconomicRegistry} from "../src/EconomicRegistry.sol";

contract EconomicRegistryTest is Test {
    EconomicRegistry registry;
    address wallet = address(0xA11CE);
    address otherWallet = address(0xB0B);
    bytes32 spendId = keccak256("spend-1");
    bytes32 goalHash = keccak256("goal-1");
    bytes32 intentHash = keccak256("intent-1");
    bytes32 paymentHash = keccak256("payment-1");

    function setUp() public {
        registry = new EconomicRegistry();
    }

    function recordSpend(address caller, bytes32 id) internal {
        vm.prank(caller);
        registry.recordSpend(id, goalHash, intentHash, paymentHash, 2_000_000);
    }

    function testRecordsImmutableSpendBoundToCallingWallet() public {
        recordSpend(wallet, spendId);
        (
            address operatingWallet,
            bytes32 storedGoal,
            bytes32 storedIntent,
            bytes32 storedPayment,
            uint256 amount,
            uint256 recordedAt,
            bool revenueLinked
        ) = registry.spendRecords(wallet, spendId);
        assertEq(operatingWallet, wallet);
        assertEq(storedGoal, goalHash);
        assertEq(storedIntent, intentHash);
        assertEq(storedPayment, paymentHash);
        assertEq(amount, 2_000_000);
        assertGt(recordedAt, 0);
        assertFalse(revenueLinked);

        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.SpendAlreadyRecorded.selector, wallet, spendId));
        registry.recordSpend(spendId, goalHash, intentHash, keccak256("changed"), 3_000_000);
    }

    function testRejectsZeroRequiredSpendFields() public {
        vm.startPrank(wallet);
        vm.expectRevert(EconomicRegistry.InvalidSpendRecord.selector);
        registry.recordSpend(bytes32(0), goalHash, intentHash, paymentHash, 1);
        vm.expectRevert(EconomicRegistry.InvalidSpendRecord.selector);
        registry.recordSpend(spendId, bytes32(0), intentHash, paymentHash, 1);
        vm.expectRevert(EconomicRegistry.InvalidSpendRecord.selector);
        registry.recordSpend(spendId, goalHash, bytes32(0), paymentHash, 1);
        vm.expectRevert(EconomicRegistry.InvalidSpendRecord.selector);
        registry.recordSpend(spendId, goalHash, intentHash, bytes32(0), 1);
        vm.expectRevert(EconomicRegistry.InvalidSpendRecord.selector);
        registry.recordSpend(spendId, goalHash, intentHash, paymentHash, 0);
        vm.stopPrank();
    }

    function testDifferentWalletsHaveIndependentNamespaces() public {
        recordSpend(wallet, spendId);
        recordSpend(otherWallet, spendId);
        (address first,,,,,,) = registry.spendRecords(wallet, spendId);
        (address second,,,,,,) = registry.spendRecords(otherWallet, spendId);
        assertEq(first, wallet);
        assertEq(second, otherWallet);
    }

    function testRecordsRevenueOnceAndLeavesSpendEvidenceAndAmountUntouched() public {
        recordSpend(wallet, spendId);
        bytes32 revenueHash = keccak256("revenue-1");
        vm.prank(wallet);
        registry.recordRevenue(spendId, revenueHash, 5_000_000, 500_000);
        (address operatingWallet, bytes32 storedGoal, bytes32 storedIntent, bytes32 storedPayment, uint256 amount,, bool linked) = registry.spendRecords(wallet, spendId);
        assertEq(operatingWallet, wallet);
        assertEq(storedGoal, goalHash);
        assertEq(storedIntent, intentHash);
        assertEq(storedPayment, paymentHash);
        assertEq(amount, 2_000_000);
        assertTrue(linked);
        (bytes32 storedSpendId, bytes32 storedRevenue, uint256 revenueAmount, uint256 earnedCapital, uint256 recordedAt) = registry.revenueRecords(wallet, spendId);
        assertEq(storedSpendId, spendId);
        assertEq(storedRevenue, revenueHash);
        assertEq(revenueAmount, 5_000_000);
        assertEq(earnedCapital, 500_000);
        assertGt(recordedAt, 0);
        assertTrue(registry.usedRevenueEvidence(revenueHash));
        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.RevenueAlreadyLinked.selector, wallet, spendId));
        registry.recordRevenue(spendId, keccak256("revenue-2"), 1, 0);
    }

    function testRejectsRevenueForUnknownSpendAndDuplicateEvidence() public {
        bytes32 revenueHash = keccak256("revenue-1");
        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.SpendNotFound.selector, wallet, spendId));
        registry.recordRevenue(spendId, revenueHash, 1, 0);
        recordSpend(wallet, spendId);
        recordSpend(otherWallet, spendId);
        vm.prank(wallet);
        registry.recordRevenue(spendId, revenueHash, 1, 0);
        vm.prank(otherWallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.RevenueAlreadyRecorded.selector, revenueHash));
        registry.recordRevenue(spendId, revenueHash, 1, 0);
    }

    function testRejectsInvalidRevenueFields() public {
        recordSpend(wallet, spendId);
        vm.startPrank(wallet);
        vm.expectRevert(EconomicRegistry.InvalidRevenueRecord.selector);
        registry.recordRevenue(spendId, bytes32(0), 1, 0);
        vm.expectRevert(EconomicRegistry.InvalidRevenueRecord.selector);
        registry.recordRevenue(spendId, keccak256("revenue-1"), 0, 0);
        vm.expectRevert(EconomicRegistry.InvalidRevenueRecord.selector);
        registry.recordRevenue(spendId, keccak256("revenue-2"), 1, 2);
        vm.stopPrank();
    }

    function testRegistryHasNoPayableOrTokenTransferEntryPoint() public {
        vm.deal(address(this), 1);
        (bool accepted,) = address(registry).call{value: 1}("");
        assertFalse(accepted);
        (accepted,) = address(registry).call(abi.encodeWithSignature("transfer(address,uint256)", wallet, 1));
        assertFalse(accepted);
        (accepted,) = address(registry).call(abi.encodeWithSignature("transferFrom(address,address,uint256)", wallet, otherWallet, 1));
        assertFalse(accepted);
    }
}
