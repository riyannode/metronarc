// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {EconomicRegistry} from "../src/EconomicRegistry.sol";

contract EconomicRegistryTest is Test {
    EconomicRegistry registry;
    address wallet = address(0xA11CE);
    bytes32 schema = keccak256("schema/1");
    bytes32 spendType = keccak256("X402_SPEND");
    bytes32 revenueType = keccak256("CIRCLE_REVENUE");
    bytes32 relationType = keccak256("SUPPORTS");

    function setUp() public {
        registry = new EconomicRegistry();
    }

    function factId(address caller, bytes32 kind, bytes32 evidence) internal view returns (bytes32) {
        return sha256(abi.encode(sha256("METRON_FACT_ID_V3"), block.chainid, address(registry), caller, kind, evidence));
    }

    function fact(bytes32 kind, bytes32 evidence) internal returns (bytes32 id) {
        id = factId(wallet, kind, evidence);
        vm.prank(wallet);
        registry.recordFact(id, kind, schema, evidence, keccak256(abi.encode(kind, evidence)));
    }

    function relation(bytes32 from, bytes32 to) internal returns (bytes32 id) {
        id = sha256(
            abi.encode(
                sha256("METRON_RELATION_ID_V3"), block.chainid, address(registry), wallet, relationType, from, to
            )
        );
        vm.prank(wallet);
        registry.recordRelationship(id, relationType, schema, from, to, keccak256(abi.encode(from, to)));
    }

    function testStandaloneRevenueAndSpend() public {
        bytes32 revenue = fact(revenueType, keccak256("receipt"));
        bytes32 spend = fact(spendType, keccak256("expense"));
        (bytes32 stored,,,,) = registry.facts(wallet, revenue);
        assertEq(stored, revenueType);
        assertEq(registry.evidenceFacts(wallet, keccak256("expense")), spend);
        assertEq(registry.VERSION(), 3);
    }

    function testManyToManyWithoutChangingFacts() public {
        bytes32 a = fact(spendType, keccak256("a"));
        bytes32 b = fact(spendType, keccak256("b"));
        bytes32 c = fact(revenueType, keccak256("c"));
        bytes32 d = fact(revenueType, keccak256("d"));
        relation(a, c);
        relation(b, c);
        relation(a, d);
        relation(b, d);
        assertEq(registry.evidenceFacts(wallet, keccak256("c")), c);
        assertEq(registry.evidenceFacts(wallet, keccak256("d")), d);
    }

    function testReplayAndConflictingRecordsRevert() public {
        bytes32 id = fact(revenueType, keccak256("receipt"));
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.AlreadyRecorded.selector);
        registry.recordFact(id, revenueType, schema, keccak256("receipt"), keccak256("changed"));
    }

    function testDuplicateSettlementAcrossTypesReverts() public {
        fact(revenueType, keccak256("receipt"));
        bytes32 id = factId(wallet, spendType, keccak256("receipt"));
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.EvidenceAlreadyUsed.selector);
        registry.recordFact(id, spendType, schema, keccak256("receipt"), keccak256("other"));
    }

    function testWrongWalletIdentityReverts() public {
        bytes32 id = factId(wallet, revenueType, keccak256("receipt"));
        vm.prank(address(0xB0B));
        vm.expectRevert(EconomicRegistry.InvalidIdentity.selector);
        registry.recordFact(id, revenueType, schema, keccak256("receipt"), keccak256("content"));
    }

    function testWrongChainAndDeploymentReplaysRevert() public {
        bytes32 id = factId(wallet, revenueType, keccak256("receipt"));
        uint256 originalChain = block.chainid;
        vm.chainId(originalChain + 1);
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.InvalidIdentity.selector);
        registry.recordFact(id, revenueType, schema, keccak256("receipt"), keccak256("content"));
        vm.chainId(originalChain);
        EconomicRegistry other = new EconomicRegistry();
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.InvalidIdentity.selector);
        other.recordFact(id, revenueType, schema, keccak256("receipt"), keccak256("content"));
    }

    function testMissingAndWrongNamespaceEndpointsRevert() public {
        bytes32 a = fact(spendType, keccak256("a"));
        bytes32 b = fact(revenueType, keccak256("b"));
        vm.prank(address(0xB0B));
        vm.expectRevert(EconomicRegistry.FactNotFound.selector);
        registry.recordRelationship(keccak256("id"), relationType, schema, a, b, keccak256("claim"));
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.FactNotFound.selector);
        registry.recordRelationship(keccak256("id"), relationType, schema, a, keccak256("missing"), keccak256("claim"));
    }

    function testDuplicateRelationshipReverts() public {
        bytes32 a = fact(spendType, keccak256("a"));
        bytes32 b = fact(revenueType, keccak256("b"));
        bytes32 id = relation(a, b);
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.AlreadyRecorded.selector);
        registry.recordRelationship(id, relationType, schema, a, b, keccak256("different"));
    }

    function testZeroAndSelfCommitmentsRevert() public {
        bytes32 a = fact(spendType, keccak256("a"));
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.InvalidCommitment.selector);
        registry.recordRelationship(keccak256("id"), relationType, schema, a, a, keccak256("claim"));
        vm.prank(wallet);
        vm.expectRevert(EconomicRegistry.InvalidCommitment.selector);
        registry.recordFact(keccak256("id"), revenueType, schema, keccak256("receipt"), bytes32(0));
    }

    function testNoNativeCustodyEntry() public {
        vm.deal(wallet, 1 ether);
        vm.prank(wallet);
        (bool ok,) = address(registry).call{value: 1}("");
        assertFalse(ok);
        assertEq(address(registry).balance, 0);
    }

    function testFutureSchemaWithoutNewABI() public {
        bytes32 kind = keccak256("FUTURE_ECONOMIC_EVENT");
        bytes32 ev = keccak256("future-source");
        bytes32 id = factId(wallet, kind, ev);
        vm.prank(wallet);
        registry.recordFact(id, kind, keccak256("future-schema/12"), ev, keccak256("future-content"));
        (bytes32 stored,,,,) = registry.facts(wallet, id);
        assertEq(stored, kind);
    }

    function testFuzzNamespacedReplay(bytes32 kind, bytes32 evidence, bytes32 content) public {
        vm.assume(kind != bytes32(0) && evidence != bytes32(0) && content != bytes32(0));
        bytes32 id = factId(wallet, kind, evidence);
        vm.startPrank(wallet);
        registry.recordFact(id, kind, schema, evidence, content);
        vm.expectRevert(EconomicRegistry.AlreadyRecorded.selector);
        registry.recordFact(id, kind, schema, evidence, content);
        vm.stopPrank();
    }
}
