// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {EconomicRegistry} from "../src/EconomicRegistry.sol";

contract RegistryVectorsTest is Test {
    function testPythonCanonicalIdentityAcceptedBySolidity() public {
        vm.chainId(5042002);
        EconomicRegistry implementation = new EconomicRegistry();
        address target = 0x4444444444444444444444444444444444444444;
        vm.etch(target, address(implementation).code);
        EconomicRegistry registry = EconomicRegistry(target);
        vm.prank(0x2222222222222222222222222222222222222222);
        registry.recordFact(
            0x6f2279337c0b3b8eaf39c3d52e78690653f19fd13b662d5fcfec0ad4b3180d3f,
            0xaa47fb48a28dba0d3b6d1bc3a52748c8a5bca90fb0518bcc009bfff9688e4515,
            0x2a4eab3e7038af7d3a4e1d4ec93cf846a4df862a3738d7e7d3723147ee48d22f,
            0x244a4190c222167efe52dea0bb126e191ab09a90a85db37db3998ec9381580b2,
            0x181e66135379c654647c5555f8c3fe9e845998be232d58e6673085c5a3a51839
        );
        (bytes32 kind, bytes32 schema, bytes32 evidence, bytes32 content,) = registry.facts(
            0x2222222222222222222222222222222222222222,
            0x6f2279337c0b3b8eaf39c3d52e78690653f19fd13b662d5fcfec0ad4b3180d3f
        );
        assertEq(kind, 0xaa47fb48a28dba0d3b6d1bc3a52748c8a5bca90fb0518bcc009bfff9688e4515);
        assertEq(schema, 0x2a4eab3e7038af7d3a4e1d4ec93cf846a4df862a3738d7e7d3723147ee48d22f);
        assertEq(evidence, 0x244a4190c222167efe52dea0bb126e191ab09a90a85db37db3998ec9381580b2);
        assertEq(content, 0x181e66135379c654647c5555f8c3fe9e845998be232d58e6673085c5a3a51839);
    }
}
