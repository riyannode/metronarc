// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title MetronVault
/// @notice Holds reserve tokens and releases bounded amounts only to the configured agent wallet.
contract MetronVault is Ownable2Step, Pausable {
    using SafeERC20 for IERC20;

    error ZeroAddress();
    error InvalidPolicy();
    error InvalidActionId();
    error ActionAlreadyUsed(bytes32 actionId);
    error InvalidAmount();
    error ActionLimitExceeded(uint256 amount, uint256 limit);
    error DailyLimitExceeded(uint256 amount, uint256 remaining);
    error ReserveFloorViolation(uint256 balanceAfter, uint256 reserveFloor);
    error InsufficientVaultBalance(uint256 balance, uint256 amount);

    IERC20 public immutable asset;
    address public agentWallet;
    uint256 public maxReleasePerAction;
    uint256 public dailyReleaseLimit;
    uint256 public reserveFloor;
    mapping(bytes32 actionId => bool used) public usedActionIds;
    mapping(uint256 day => uint256 released) public releasedByDay;

    event AgentWalletChanged(address indexed oldWallet, address indexed newWallet);
    event PolicyChanged(uint256 maxReleasePerAction, uint256 dailyReleaseLimit, uint256 reserveFloor);
    event OperatingCapitalReleased(
        bytes32 indexed actionId,
        address indexed agentWallet,
        uint256 amount,
        bytes32 indexed documentHash,
        bytes32 reasonHash
    );
    event EmergencyWithdrawal(address indexed to, uint256 amount);

    modifier onlyAgentWallet() {
        if (msg.sender != agentWallet) revert OwnableUnauthorizedAccount(msg.sender);
        _;
    }

    /// @param asset_ ERC20 held as the reserve asset.
    /// @param agentWallet_ Circle Agent Wallet address allowed to request releases.
    /// @param maxPerAction_ Maximum token amount released by one action.
    /// @param dailyLimit_ Maximum token amount released in a UTC day.
    /// @param reserveFloor_ Minimum token balance retained in the vault after release.
    constructor(IERC20 asset_, address agentWallet_, uint256 maxPerAction_, uint256 dailyLimit_, uint256 reserveFloor_)
        Ownable(msg.sender)
    {
        if (address(asset_) == address(0) || agentWallet_ == address(0)) revert ZeroAddress();
        _validatePolicy(maxPerAction_, dailyLimit_);
        asset = asset_;
        agentWallet = agentWallet_;
        maxReleasePerAction = maxPerAction_;
        dailyReleaseLimit = dailyLimit_;
        reserveFloor = reserveFloor_;
        emit AgentWalletChanged(address(0), agentWallet_);
        emit PolicyChanged(maxPerAction_, dailyLimit_, reserveFloor_);
    }

    /// @notice Release bounded reserve capital to the configured agent wallet.
    /// @param actionId Unique off-chain Spend Intent or release identifier.
    /// @param amount Exact token amount to release.
    /// @param documentHash Hash of the source economic document.
    /// @param reasonHash Hash of the human-readable reason kept off-chain.
    function releaseOperatingCapital(bytes32 actionId, uint256 amount, bytes32 documentHash, bytes32 reasonHash)
        external
        onlyAgentWallet
        whenNotPaused
    {
        if (actionId == bytes32(0)) revert InvalidActionId();
        if (usedActionIds[actionId]) revert ActionAlreadyUsed(actionId);
        if (amount == 0) revert InvalidAmount();
        if (amount > maxReleasePerAction) revert ActionLimitExceeded(amount, maxReleasePerAction);

        uint256 day = block.timestamp / 1 days;
        uint256 released = releasedByDay[day];
        if (released >= dailyReleaseLimit) revert DailyLimitExceeded(amount, 0);
        uint256 remaining = dailyReleaseLimit - released;
        if (amount > remaining) revert DailyLimitExceeded(amount, remaining);

        uint256 balance = asset.balanceOf(address(this));
        if (amount > balance) revert InsufficientVaultBalance(balance, amount);
        uint256 balanceAfter = balance - amount;
        if (balanceAfter < reserveFloor) revert ReserveFloorViolation(balanceAfter, reserveFloor);

        usedActionIds[actionId] = true;
        releasedByDay[day] = released + amount;
        asset.safeTransfer(agentWallet, amount);
        emit OperatingCapitalReleased(actionId, agentWallet, amount, documentHash, reasonHash);
    }

    /// @notice Set the Circle Agent Wallet authorized to request releases.
    function setAgentWallet(address newWallet) external onlyOwner {
        if (newWallet == address(0)) revert ZeroAddress();
        address oldWallet = agentWallet;
        agentWallet = newWallet;
        emit AgentWalletChanged(oldWallet, newWallet);
    }

    /// @notice Update the action limit, daily limit, and reserve floor.
    function setPolicy(uint256 maxPerAction, uint256 dailyLimit, uint256 newReserveFloor) external onlyOwner {
        _validatePolicy(maxPerAction, dailyLimit);
        maxReleasePerAction = maxPerAction;
        dailyReleaseLimit = dailyLimit;
        reserveFloor = newReserveFloor;
        emit PolicyChanged(maxPerAction, dailyLimit, newReserveFloor);
    }

    /// @notice Pause all agent releases.
    function pause() external onlyOwner {
        _pause();
    }

    /// @notice Resume agent releases.
    function unpause() external onlyOwner {
        _unpause();
    }

    /// @notice Withdraw tokens to an owner-selected address while the vault is paused.
    function emergencyWithdraw(address to, uint256 amount) external onlyOwner whenPaused {
        if (to == address(0)) revert ZeroAddress();
        if (amount == 0) revert InvalidAmount();
        asset.safeTransfer(to, amount);
        emit EmergencyWithdrawal(to, amount);
    }

    function _validatePolicy(uint256 maxPerAction, uint256 dailyLimit) private pure {
        if (maxPerAction == 0 || dailyLimit < maxPerAction) revert InvalidPolicy();
    }
}
