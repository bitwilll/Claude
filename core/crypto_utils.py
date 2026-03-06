"""
Low-level cryptographic utilities for BITWILL.
Handles hashing, key derivation, HMAC, and encoding used throughout the wallet.
"""

import hashlib
import hmac
import struct
import os
import secrets
from typing import Tuple

import base58


# Bitcoin network version bytes
MAINNET_PRIVATE = b'\x04\x88\xAD\xE4'  # xprv
MAINNET_PUBLIC = b'\x04\x88\xB2\x1E'   # xpub
TESTNET_PRIVATE = b'\x04\x35\x83\x94'  # tprv
TESTNET_PUBLIC = b'\x04\x35\x87\xCF'   # tpub

MAINNET_WIF_PREFIX = b'\x80'
TESTNET_WIF_PREFIX = b'\xEF'

MAINNET_P2PKH_PREFIX = b'\x00'
TESTNET_P2PKH_PREFIX = b'\x6F'

MAINNET_P2SH_PREFIX = b'\x05'
TESTNET_P2SH_PREFIX = b'\xC4'

# Secp256k1 curve order
SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_GEN_X = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
SECP256K1_GEN_Y = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
SECP256K1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def double_sha256(data: bytes) -> bytes:
    return sha256(sha256(data))


def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data)) - used for Bitcoin addresses."""
    sha = sha256(data)
    ripemd = hashlib.new('ripemd160')
    ripemd.update(sha)
    return ripemd.digest()


def hmac_sha512(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha512).digest()


def base58check_encode(version: bytes, payload: bytes) -> str:
    data = version + payload
    checksum = double_sha256(data)[:4]
    return base58.b58encode(data + checksum).decode('ascii')


def base58check_decode(address: str) -> Tuple[bytes, bytes]:
    raw = base58.b58decode(address)
    version = raw[:1]
    payload = raw[1:-4]
    checksum = raw[-4:]
    expected = double_sha256(version + payload)[:4]
    if checksum != expected:
        raise ValueError("Invalid Base58Check checksum")
    return version, payload


def generate_entropy(strength: int = 256) -> bytes:
    """Generate cryptographically secure random bytes."""
    if strength not in (128, 160, 192, 224, 256):
        raise ValueError("Strength must be 128, 160, 192, 224, or 256 bits")
    return secrets.token_bytes(strength // 8)


def private_key_to_wif(privkey: bytes, compressed: bool = True,
                       testnet: bool = False) -> str:
    prefix = TESTNET_WIF_PREFIX if testnet else MAINNET_WIF_PREFIX
    payload = privkey
    if compressed:
        payload = privkey + b'\x01'
    return base58check_encode(prefix, payload)


def wif_to_private_key(wif: str) -> Tuple[bytes, bool, bool]:
    """Returns (private_key_bytes, compressed, testnet)."""
    version, payload = base58check_decode(wif)
    testnet = (version == TESTNET_WIF_PREFIX)
    if len(payload) == 33 and payload[-1] == 0x01:
        return payload[:-1], True, testnet
    return payload, False, testnet


def int_to_bytes(n: int, length: int = 32) -> bytes:
    return n.to_bytes(length, byteorder='big')


def bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, byteorder='big')


# --- Secp256k1 elliptic curve arithmetic (pure Python) ---

def modinv(a: int, m: int = SECP256K1_P) -> int:
    return pow(a, m - 2, m)


def ec_add(p1: Tuple[int, int], p2: Tuple[int, int]) -> Tuple[int, int]:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and y1 != y2:
        return None  # point at infinity
    if x1 == x2:
        lam = (3 * x1 * x1 * modinv(2 * y1)) % SECP256K1_P
    else:
        lam = ((y2 - y1) * modinv(x2 - x1)) % SECP256K1_P
    x3 = (lam * lam - x1 - x2) % SECP256K1_P
    y3 = (lam * (x1 - x3) - y1) % SECP256K1_P
    return (x3, y3)


def ec_multiply(point: Tuple[int, int], scalar: int) -> Tuple[int, int]:
    result = None
    addend = point
    while scalar:
        if scalar & 1:
            result = ec_add(result, addend)
        addend = ec_add(addend, addend)
        scalar >>= 1
    return result


SECP256K1_G = (SECP256K1_GEN_X, SECP256K1_GEN_Y)


def privkey_to_pubkey(privkey: bytes, compressed: bool = True) -> bytes:
    scalar = bytes_to_int(privkey)
    point = ec_multiply(SECP256K1_G, scalar)
    if compressed:
        prefix = b'\x02' if point[1] % 2 == 0 else b'\x03'
        return prefix + int_to_bytes(point[0])
    return b'\x04' + int_to_bytes(point[0]) + int_to_bytes(point[1])


def pubkey_to_address(pubkey: bytes, testnet: bool = False) -> str:
    h = hash160(pubkey)
    prefix = TESTNET_P2PKH_PREFIX if testnet else MAINNET_P2PKH_PREFIX
    return base58check_encode(prefix, h)


def compress_pubkey(pubkey: bytes) -> bytes:
    if len(pubkey) == 33:
        return pubkey
    if len(pubkey) != 65 or pubkey[0] != 0x04:
        raise ValueError("Invalid uncompressed public key")
    x = pubkey[1:33]
    y_int = bytes_to_int(pubkey[33:65])
    prefix = b'\x02' if y_int % 2 == 0 else b'\x03'
    return prefix + x


def decompress_pubkey(pubkey: bytes) -> bytes:
    if len(pubkey) == 65:
        return pubkey
    if len(pubkey) != 33:
        raise ValueError("Invalid compressed public key")
    prefix = pubkey[0]
    x = bytes_to_int(pubkey[1:33])
    # y^2 = x^3 + 7 (mod p)
    y_sq = (pow(x, 3, SECP256K1_P) + 7) % SECP256K1_P
    y = pow(y_sq, (SECP256K1_P + 1) // 4, SECP256K1_P)
    if (y % 2 == 0) != (prefix == 0x02):
        y = SECP256K1_P - y
    return b'\x04' + int_to_bytes(x) + int_to_bytes(y)


def serialize_extended_key(version: bytes, depth: int, fingerprint: bytes,
                           child_number: int, chain_code: bytes,
                           key_data: bytes) -> str:
    raw = (version +
           struct.pack('B', depth) +
           fingerprint +
           struct.pack('>I', child_number) +
           chain_code +
           key_data)
    checksum = double_sha256(raw)[:4]
    return base58.b58encode(raw + checksum).decode('ascii')
