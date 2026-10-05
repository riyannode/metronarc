// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {MetronVault} from "../src/MetronVault.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract MetronVaultTest is Test {
    event Paused(address account);
    event Unpaused(address account);

    MockUSDC token;
    MetronVault vault;
    address agent = address(0xA11CE);
    address outsider = address(0xBAD);
    uint256 constant UNIT = 1e6;

    function setUp() public {
        token = new MockUSDC();
        vault = new MetronVault(token, agent, 10 * UNIT, 20 * UNIT, 5 * UNIT);
        token.mint(address(vault), 100 * UNIT);
    }

    function release(bytes32 id, uint256 amount) internal {
        vm.prank(agent);
        vault.releaseOperatingCapital(id, amount, bytes32(uint256(1)), bytes32(uint256(2)));
    }

    function testConstructorInitializesAndOwnerControlsPolicy() public {
        assertEq(vault.owner(), address(this));
        assertEq(address(vault.asset()), address(token));
        assertEq(vault.agentWallet(), agent);
        assertEq(vault.maxReleasePerAction(), 10 * UNIT);
        assertEq(vault.dailyReleaseLimit(), 20 * UNIT);
        assertEq(vault.reserveFloor(), 5 * UNIT);
        vm.expectEmit(false, false, false, true);
        emit MetronVault.PolicyChanged(8 * UNIT, 12 * UNIT, 6 * UNIT);
        vault.setPolicy(8 * UNIT, 12 * UNIT, 6 * UNIT);
        assertEq(vault.maxReleasePerAction(), 8 * UNIT);
        vm.expectRevert(MetronVault.InvalidPolicy.selector);
        vault.setPolicy(13 * UNIT, 12 * UNIT, 6 * UNIT);
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, outsider));
        vault.setPolicy(8 * UNIT, 12 * UNIT, 6 * UNIT);
    }

    function testConstructorEmitsInitialAdminEvents() public {
        vm.expectEmit(true, true, false, true);
        emit MetronVault.AgentWalletChanged(address(0), agent);
        vm.expectEmit(false, false, false, true);
        emit MetronVault.PolicyChanged(10 * UNIT, 20 * UNIT, 5 * UNIT);
        new MetronVault(token, agent, 10 * UNIT, 20 * UNIT, 5 * UNIT);
    }

    function testConstructorRejectsInvalidInputs() public {
        vm.expectRevert(MetronVault.ZeroAddress.selector);
        new MetronVault(token, address(0), UNIT, UNIT, 0);
        vm.expectRevert(MetronVault.ZeroAddress.selector);
        new MetronVault(MockUSDC(address(0)), agent, UNIT, UNIT, 0);
        vm.expectRevert(MetronVault.InvalidPolicy.selector);
        new MetronVault(token, agent, 0, UNIT, 0);
        vm.expectRevert(MetronVault.InvalidPolicy.selector);
        new MetronVault(token, agent, 2 * UNIT, UNIT, 0);
    }

    function testNonOwnerCannotRotateWalletOrPauseVault() public {
        vm.startPrank(outsider);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, outsider));
        vault.setAgentWallet(address(0xB0B));
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, outsider));
        vault.pause();
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, outsider));
        vault.unpause();
        vm.stopPrank();
    }

    function testOnlyAgentCanRelease() public {
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, outsider));
        vault.releaseOperatingCapital(bytes32(uint256(1)), UNIT, bytes32(0), bytes32(0));
    }

    function testRejectsZeroAndDuplicateActionIds() public {
        vm.expectRevert(MetronVault.InvalidActionId.selector);
        release(bytes32(0), UNIT);
        bytes32 id = bytes32(uint256(3));
        release(id, UNIT);
        vm.expectRevert(abi.encodeWithSelector(MetronVault.ActionAlreadyUsed.selector, id));
        release(id, UNIT);
    }

    function testRejectsZeroAmountAndActionLimit() public {
        vm.expectRevert(MetronVault.InvalidAmount.selector);
        release(bytes32(uint256(4)), 0);
        vm.expectRevert(abi.encodeWithSelector(MetronVault.ActionLimitExceeded.selector, 11 * UNIT, 10 * UNIT));
        release(bytes32(uint256(5)), 11 * UNIT);
    }

    function testRejectsDailyLimitAndResetsNextDay() public {
        release(bytes32(uint256(6)), 10 * UNIT);
        release(bytes32(uint256(7)), 10 * UNIT);
        uint256 currentDay = vm.getBlockTimestamp() / 1 days;
        assertEq(vault.releasedByDay(currentDay), 20 * UNIT);
        vm.expectRevert(abi.encodeWithSelector(MetronVault.DailyLimitExceeded.selector, UNIT, 0));
        release(bytes32(uint256(8)), UNIT);
        vm.warp((currentDay + 1) * 1 days);
        release(bytes32(uint256(8)), UNIT);
        assertEq(vault.releasedByDay(block.timestamp / 1 days), UNIT);
    }

    function testReserveFloorAndInsufficientBalance() public {
        vault.setPolicy(101 * UNIT, 101 * UNIT, 5 * UNIT);
        vm.expectRevert(abi.encodeWithSelector(MetronVault.ReserveFloorViolation.selector, 4 * UNIT, 5 * UNIT));
        release(bytes32(uint256(9)), 96 * UNIT);
        vm.expectRevert(abi.encodeWithSelector(MetronVault.InsufficientVaultBalance.selector, 100 * UNIT, 101 * UNIT));
        release(bytes32(uint256(10)), 101 * UNIT);
    }

    function testSuccessfulReleaseTransfersMarksActionUpdatesDailyAndEmits() public {
        bytes32 id = bytes32(uint256(11));
        vm.expectEmit(true, true, true, true);
        emit MetronVault.OperatingCapitalReleased(id, agent, 3 * UNIT, bytes32(uint256(1)), bytes32(uint256(2)));
        release(id, 3 * UNIT);
        assertEq(token.balanceOf(agent), 3 * UNIT);
        assertTrue(vault.usedActionIds(id));
        assertEq(vault.releasedByDay(block.timestamp / 1 days), 3 * UNIT);
    }

    function testPauseBlocksReleaseAndUnpauseRestoresIt() public {
        vm.expectEmit(false, false, false, true);
        emit Paused(address(this));
        vault.pause();
        vm.expectRevert();
        release(bytes32(uint256(12)), UNIT);
        vm.expectEmit(false, false, false, true);
        emit Unpaused(address(this));
        vault.unpause();
        release(bytes32(uint256(12)), UNIT);
    }

    function testAgentRotationAndZeroAddressRejection() public {
        address next = address(0xB0B);
        vm.expectEmit(true, true, false, true);
        emit MetronVault.AgentWalletChanged(agent, next);
        vault.setAgentWallet(next);
        assertEq(vault.agentWallet(), next);
        vm.expectRevert(MetronVault.ZeroAddress.selector);
        vault.setAgentWallet(address(0));
    }

    function testEmergencyWithdrawalRequiresPauseAndOwner() public {
        vm.expectRevert();
        vault.emergencyWithdraw(address(this), UNIT);
        vault.pause();
        vm.prank(outsider);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, outsider));
        vault.emergencyWithdraw(address(this), UNIT);
        uint256 beforeBalance = token.balanceOf(address(this));
        vm.expectEmit(false, false, false, true);
        emit MetronVault.EmergencyWithdrawal(address(this), UNIT);
        vault.emergencyWithdraw(address(this), UNIT);
        assertEq(token.balanceOf(address(this)), beforeBalance + UNIT);
    }
}
