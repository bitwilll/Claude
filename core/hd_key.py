"""
BIP-32 Hierarchical Deterministic Key Derivation for BITWILL.
Implements master key generation, child key derivation (normal and hardened),
and derivation path parsing (BIP-44 compatible).
"""

import struct
from typing import Optional, Tuple, List
from dataclasses import dataclass, field

from .crypto_utils import (
    hmac_sha512, hash160, privkey_to_pubkey, compress_pubkey,
    ec_add, ec_multiply, SECP256K1_G, SECP256K1_ORDER,
    bytes_to_int, int_to_bytes, serialize_extended_key,
    MAINNET_PRIVATE, MAINNET_PUBLIC, TESTNET_PRIVATE, TESTNET_PUBLIC,
    pubkey_to_address, private_key_to_wif
)

HARDENED_OFFSET = 0x80000000


@dataclass
class HDKey:
    """Represents a BIP-32 extended key (private or public)."""
    private_key: Optional[bytes] = None
    public_key: bytes = b''
    chain_code: bytes = b''
    depth: int = 0
    fingerprint: bytes = b'\x00\x00\x00\x00'
    child_number: int = 0
    testnet: bool = False

    @property
    def is_private(self) -> bool:
        return self.private_key is not None

    @property
    def address(self) -> str:
        return pubkey_to_address(self.public_key, self.testnet)

    @property
    def wif(self) -> Optional[str]:
        if self.private_key:
            return private_key_to_wif(self.private_key, compressed=True,
                                      testnet=self.testnet)
        return None

    def xprv(self) -> Optional[str]:
        if not self.is_private:
            return None
        version = TESTNET_PRIVATE if self.testnet else MAINNET_PRIVATE
        return serialize_extended_key(
            version, self.depth, self.fingerprint,
            self.child_number, self.chain_code, b'\x00' + self.private_key
        )

    def xpub(self) -> str:
        version = TESTNET_PUBLIC if self.testnet else MAINNET_PUBLIC
        return serialize_extended_key(
            version, self.depth, self.fingerprint,
            self.child_number, self.chain_code, self.public_key
        )

    def identifier(self) -> bytes:
        return hash160(self.public_key)

    def parent_fingerprint(self) -> bytes:
        return self.identifier()[:4]


def master_key_from_seed(seed: bytes, testnet: bool = False) -> HDKey:
    """
    Generate a BIP-32 master key from a seed (typically from BIP-39 mnemonic).
    Uses HMAC-SHA512 with key "Bitcoin seed".
    """
    I = hmac_sha512(b"Bitcoin seed", seed)
    IL, IR = I[:32], I[32:]

    # Validate private key
    key_int = bytes_to_int(IL)
    if key_int == 0 or key_int >= SECP256K1_ORDER:
        raise ValueError("Invalid master key derived from seed")

    pubkey = privkey_to_pubkey(IL, compressed=True)

    return HDKey(
        private_key=IL,
        public_key=pubkey,
        chain_code=IR,
        depth=0,
        fingerprint=b'\x00\x00\x00\x00',
        child_number=0,
        testnet=testnet
    )


def derive_child_key(parent: HDKey, index: int) -> HDKey:
    """
    Derive a child key from a parent key at the given index.
    For hardened derivation, use index >= HARDENED_OFFSET (or use derive_path).
    """
    hardened = index >= HARDENED_OFFSET

    if hardened:
        if not parent.is_private:
            raise ValueError("Cannot derive hardened child from public key")
        data = b'\x00' + parent.private_key + struct.pack('>I', index)
    else:
        data = parent.public_key + struct.pack('>I', index)

    I = hmac_sha512(parent.chain_code, data)
    IL, IR = I[:32], I[32:]
    IL_int = bytes_to_int(IL)

    if IL_int >= SECP256K1_ORDER:
        raise ValueError("Invalid child key")

    fp = parent.identifier()[:4]

    if parent.is_private:
        child_key_int = (IL_int + bytes_to_int(parent.private_key)) % SECP256K1_ORDER
        if child_key_int == 0:
            raise ValueError("Invalid child key (zero)")
        child_privkey = int_to_bytes(child_key_int)
        child_pubkey = privkey_to_pubkey(child_privkey, compressed=True)

        return HDKey(
            private_key=child_privkey,
            public_key=child_pubkey,
            chain_code=IR,
            depth=parent.depth + 1,
            fingerprint=fp,
            child_number=index,
            testnet=parent.testnet
        )
    else:
        # Public key derivation
        parent_point = _pubkey_to_point(parent.public_key)
        child_point = ec_add(parent_point, ec_multiply(SECP256K1_G, IL_int))
        if child_point is None:
            raise ValueError("Invalid child key (point at infinity)")

        prefix = b'\x02' if child_point[1] % 2 == 0 else b'\x03'
        child_pubkey = prefix + int_to_bytes(child_point[0])

        return HDKey(
            private_key=None,
            public_key=child_pubkey,
            chain_code=IR,
            depth=parent.depth + 1,
            fingerprint=fp,
            child_number=index,
            testnet=parent.testnet
        )


def _pubkey_to_point(pubkey: bytes) -> Tuple[int, int]:
    """Convert compressed public key to EC point."""
    from .crypto_utils import decompress_pubkey
    uncompressed = decompress_pubkey(pubkey)
    x = bytes_to_int(uncompressed[1:33])
    y = bytes_to_int(uncompressed[33:65])
    return (x, y)


def parse_derivation_path(path: str) -> List[int]:
    """
    Parse a BIP-32 derivation path string.
    e.g., "m/44'/0'/0'/0/0" -> [0x8000002C, 0x80000000, 0x80000000, 0, 0]
    """
    if not path.startswith('m'):
        raise ValueError(f"Invalid derivation path: {path}")

    parts = path.split('/')
    if parts[0] != 'm':
        raise ValueError(f"Path must start with 'm': {path}")

    indices = []
    for part in parts[1:]:
        if not part:
            continue
        hardened = part.endswith("'") or part.endswith("h")
        index = int(part.rstrip("'h"))
        if hardened:
            index += HARDENED_OFFSET
        indices.append(index)

    return indices


def derive_path(master: HDKey, path: str) -> HDKey:
    """Derive a key from a master key using a BIP-32 path string."""
    indices = parse_derivation_path(path)
    key = master
    for index in indices:
        key = derive_child_key(key, index)
    return key


# BIP-44 standard paths
def bip44_path(account: int = 0, change: int = 0, address_index: int = 0,
               testnet: bool = False) -> str:
    """Generate a BIP-44 derivation path for Bitcoin."""
    coin_type = 1 if testnet else 0
    return f"m/44'/{coin_type}'/{account}'/{change}/{address_index}"
