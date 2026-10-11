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

    function recordRevenue(address caller, bytes32 id, bytes32 evidence) internal {
        vm.prank(caller);
        registry.recordRevenue(id, evidence, 5_000_000, 500_000);
    }

    function testVersionIsTwo() public view {
        assertEq(registry.VERSION(), "2");
    }

    function testRecordsImmutableSpendAndRejectsDuplicate() public {
        recordSpend(wallet, spendId);
        (
            address operatingWallet,
            bytes32 storedGoal,
            bytes32 storedIntent,
            bytes32 storedPayment,
            uint256 amount,
            uint256 recordedAt,
            uint256 revenueCount
        ) = registry.spendRecords(wallet, spendId);
        assertEq(operatingWallet, wallet);
        assertEq(storedGoal, goalHash);
        assertEq(storedIntent, intentHash);
        assertEq(storedPayment, paymentHash);
        assertEq(amount, 2_000_000);
        assertGt(recordedAt, 0);
        assertEq(revenueCount, 0);

        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.SpendAlreadyRecorded.selector, wallet, spendId));
        registry.recordSpend(spendId, goalHash, intentHash, keccak256("changed"), 3_000_000);
    }

    function testRejectsInvalidSpend() public {
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

    function testDifferentWalletsHaveIndependentSpendNamespaces() public {
        recordSpend(wallet, spendId);
        recordSpend(otherWallet, spendId);
        (address first,,,,,,) = registry.spendRecords(wallet, spendId);
        (address second,,,,,,) = registry.spendRecords(otherWallet, spendId);
        assertEq(first, wallet);
        assertEq(second, otherWallet);
    }

    function testThreeDistinctRevenuesCanLinkToOneSpend() public {
        recordSpend(wallet, spendId);
        bytes32 first = keccak256("revenue-1");
        bytes32 second = keccak256("revenue-2");
        bytes32 third = keccak256("revenue-3");

        recordRevenue(wallet, spendId, first);
        recordRevenue(wallet, spendId, second);
        recordRevenue(wallet, spendId, third);

        (,,,,,, uint256 revenueCount) = registry.spendRecords(wallet, spendId);
        assertEq(revenueCount, 3);
        assertRevenue(wallet, spendId, first);
        assertRevenue(wallet, spendId, second);
        assertRevenue(wallet, spendId, third);
    }

    function assertRevenue(address caller, bytes32 id, bytes32 evidence) internal view {
        (bytes32 storedSpendId, bytes32 storedEvidence, uint256 amount, uint256 earned, uint256 recordedAt) =
            registry.revenueRecords(caller, id, evidence);
        assertEq(storedSpendId, id);
        assertEq(storedEvidence, evidence);
        assertEq(amount, 5_000_000);
        assertEq(earned, 500_000);
        assertGt(recordedAt, 0);
        assertTrue(registry.usedRevenueEvidence(caller, evidence));
    }

    function testDuplicateRevenueEvidenceForSameSpendIsRejected() public {
        recordSpend(wallet, spendId);
        bytes32 evidence = keccak256("revenue-1");
        recordRevenue(wallet, spendId, evidence);

        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.RevenueAlreadyRecorded.selector, wallet, evidence));
        registry.recordRevenue(spendId, evidence, 5_000_000, 500_000);
    }

    function testRevenueEvidenceCannotBeReusedForAnotherSpend() public {
        bytes32 otherSpendId = keccak256("spend-2");
        bytes32 evidence = keccak256("revenue-1");
        recordSpend(wallet, spendId);
        recordSpend(wallet, otherSpendId);
        recordRevenue(wallet, spendId, evidence);

        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.RevenueAlreadyRecorded.selector, wallet, evidence));
        registry.recordRevenue(otherSpendId, evidence, 5_000_000, 500_000);
    }

    function testRejectsRevenueForUnknownSpend() public {
        vm.prank(wallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.SpendNotFound.selector, wallet, spendId));
        registry.recordRevenue(spendId, keccak256("revenue-1"), 1, 0);
    }

    function testRejectsInvalidRevenue() public {
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

    function testDifferentWalletsMayUseSameRevenueEvidenceIndependently() public {
        bytes32 evidence = keccak256("revenue-1");
        recordSpend(wallet, spendId);
        recordSpend(otherWallet, spendId);
        recordRevenue(wallet, spendId, evidence);
        recordRevenue(otherWallet, spendId, evidence);
        assertRevenue(wallet, spendId, evidence);
        assertRevenue(otherWallet, spendId, evidence);
    }

    function testWalletCannotAttachRevenueToAnotherWalletsSpend() public {
        recordSpend(wallet, spendId);
        vm.prank(otherWallet);
        vm.expectRevert(abi.encodeWithSelector(EconomicRegistry.SpendNotFound.selector, otherWallet, spendId));
        registry.recordRevenue(spendId, keccak256("revenue-1"), 1, 0);
    }

    function testRegistryHasNoPayableOrTokenTransferEntryPoint() public {
        vm.deal(address(this), 1);
        (bool accepted,) = address(registry).call{value: 1}("");
        assertFalse(accepted);
        (accepted,) = address(registry).call(abi.encodeWithSignature("transfer(address,uint256)", wallet, 1));
        assertFalse(accepted);
        (accepted,) = address(registry)
            .call(abi.encodeWithSignature("transferFrom(address,address,uint256)", wallet, otherWallet, 1));
        assertFalse(accepted);
    }
}
