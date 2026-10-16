from __future__ import annotations

import hashlib
import json
from pathlib import Path

import circle
import store
from registry_hashing import RegistryError, address

RELEASE = Path(__file__).resolve().parents[1] / 'references/registry-v3-release.json'
V2_ADDRESS = '0x547552585d8d995c5063820b2950e0db52b4cab4'


def release() -> dict:
    try:
        data = json.loads(RELEASE.read_text())
        abi_hash = hashlib.sha256(json.dumps(data['abi'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (data['schema'] != 'metron.registry-release/3' or abi_hash != data['abi_sha256']
                or not data['runtime_bytecode'].startswith('0x')
                or hashlib.sha256(bytes.fromhex(data['runtime_bytecode'][2:])).hexdigest() != data['runtime_sha256']):
            raise ValueError
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise RegistryError('METRON_REGISTRY_RELEASE_INVALID') from None


def binding(contract: str, wallet: str) -> dict:
    artifact = release()
    return {'chain_id': '5042002', 'registry': address(contract), 'wallet': address(wallet),
            'abi_sha256': artifact['abi_sha256'], 'runtime_sha256': artifact['runtime_sha256']}


def approved(config: dict) -> bool:
    return config.get('registry_v3_verification') == binding(config.get('registry_v3_address'), config.get('operating_wallet'))


def activate(contract: str, *, operator_confirmed: bool = False) -> dict:
    if operator_confirmed is not True:
        raise RegistryError('METRON_REGISTRY_ACTIVATION_REQUIRED')
    config = store.read_config()
    if config.get('chain', 'ARC-TESTNET') != 'ARC-TESTNET' or address(contract) == V2_ADDRESS:
        raise RegistryError('METRON_REGISTRY_CONTRACT_MISMATCH')
    verified = binding(contract, config.get('operating_wallet'))
    inspected = circle.registry_v3_inspect(verified['registry'])
    if inspected != {'chain_id': '5042002', 'runtime_sha256': verified['runtime_sha256'], 'version': '3'}:
        raise RegistryError('METRON_REGISTRY_CONTRACT_MISMATCH')
    config.update(registry_v3_address=verified['registry'], registry_v3_enabled=True, registry_v3_verification=verified)
    store.write_config(config)
    return {'status': 'ACTIVE', 'verification': verified, 'backlog_dispatch': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Verify the pinned V3 release against a local Foundry build')
    parser.add_argument('--check-build', action='store_true', required=True)
    parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    built = json.loads((root / 'contracts/out/EconomicRegistry.sol/EconomicRegistry.json').read_text())
    artifact = release()
    runtime = built['deployedBytecode']['object'].removeprefix('0x')
    if ('0x' + runtime != artifact['runtime_bytecode'] or built['abi'] != artifact['abi']
            or hashlib.sha256((root / 'contracts/src/EconomicRegistry.sol').read_bytes()).hexdigest() != artifact['source_sha256']):
        raise RegistryError('METRON_REGISTRY_RELEASE_INVALID')
    print('Pinned V3 ABI, runtime bytecode and source: PASS')
