"""
Encrypted storage backend for BITWILL.
Handles secure persistence of wallet data, keys, and pre-signed transactions.
Uses AES-256-GCM for encryption with Argon2-like key derivation (PBKDF2 fallback).
"""

import json
import os
import hashlib
import struct
import time
from typing import Any, Dict, Optional

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


STORAGE_VERSION = 1
PBKDF2_ITERATIONS = 600_000
SALT_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16


def derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Derive a 256-bit encryption key from a password using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations,
        dklen=32
    )


def encrypt_data(plaintext: bytes, password: str) -> bytes:
    """
    Encrypt data with AES-256-GCM.
    Returns: version(1) + salt(32) + nonce(12) + tag(16) + ciphertext
    """
    salt = get_random_bytes(SALT_SIZE)
    key = derive_key(password, salt)
    nonce = get_random_bytes(NONCE_SIZE)

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)

    return (struct.pack('B', STORAGE_VERSION) +
            salt + nonce + tag + ciphertext)


def decrypt_data(encrypted: bytes, password: str) -> bytes:
    """Decrypt AES-256-GCM encrypted data."""
    offset = 0
    version = struct.unpack('B', encrypted[offset:offset + 1])[0]
    offset += 1

    if version != STORAGE_VERSION:
        raise ValueError(f"Unsupported storage version: {version}")

    salt = encrypted[offset:offset + SALT_SIZE]
    offset += SALT_SIZE

    nonce = encrypted[offset:offset + NONCE_SIZE]
    offset += NONCE_SIZE

    tag = encrypted[offset:offset + TAG_SIZE]
    offset += TAG_SIZE

    ciphertext = encrypted[offset:]

    key = derive_key(password, salt)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    return plaintext


class EncryptedStore:
    """
    Encrypted file-based storage for wallet data.
    All data is encrypted at rest with AES-256-GCM.
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def _file_path(self, name: str) -> str:
        return os.path.join(self.storage_dir, f"{name}.enc")

    def save(self, name: str, data: Dict[str, Any], password: str) -> None:
        """Encrypt and save JSON-serializable data."""
        plaintext = json.dumps(data, indent=2, default=str).encode('utf-8')
        encrypted = encrypt_data(plaintext, password)
        path = self._file_path(name)
        # Write atomically
        tmp_path = path + '.tmp'
        with open(tmp_path, 'wb') as f:
            f.write(encrypted)
        os.replace(tmp_path, path)

    def load(self, name: str, password: str) -> Dict[str, Any]:
        """Load and decrypt stored data."""
        path = self._file_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No stored data found: {name}")
        with open(path, 'rb') as f:
            encrypted = f.read()
        plaintext = decrypt_data(encrypted, password)
        return json.loads(plaintext.decode('utf-8'))

    def exists(self, name: str) -> bool:
        return os.path.exists(self._file_path(name))

    def delete(self, name: str) -> None:
        path = self._file_path(name)
        if os.path.exists(path):
            # Overwrite before deletion for security
            size = os.path.getsize(path)
            with open(path, 'wb') as f:
                f.write(get_random_bytes(size))
            os.remove(path)

    def list_entries(self) -> list:
        entries = []
        for f in os.listdir(self.storage_dir):
            if f.endswith('.enc'):
                entries.append(f[:-4])
        return entries
