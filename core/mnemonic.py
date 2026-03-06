"""
BIP-39 Mnemonic implementation for BITWILL.
Generates and validates mnemonic seed phrases for wallet recovery.
"""

import hashlib
import unicodedata
import secrets
from typing import List, Optional

# BIP-39 English wordlist (2048 words)
# We embed the wordlist directly for portability
BIP39_WORDLIST_URL = "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt"

# The full 2048-word BIP39 English wordlist
BIP39_ENGLISH = None  # Loaded lazily


def _load_wordlist() -> List[str]:
    """Load the BIP39 English wordlist from embedded data or file."""
    global BIP39_ENGLISH
    if BIP39_ENGLISH is not None:
        return BIP39_ENGLISH

    import os
    wordlist_path = os.path.join(os.path.dirname(__file__), 'bip39_english.txt')
    if os.path.exists(wordlist_path):
        with open(wordlist_path, 'r') as f:
            BIP39_ENGLISH = [w.strip() for w in f.readlines() if w.strip()]
    else:
        # Fallback: try to use the mnemonic library
        try:
            from mnemonic import Mnemonic
            m = Mnemonic("english")
            BIP39_ENGLISH = m.wordlist
        except ImportError:
            raise RuntimeError(
                "BIP39 wordlist not found. Place bip39_english.txt in core/ "
                "or install the 'mnemonic' package."
            )

    if len(BIP39_ENGLISH) != 2048:
        raise RuntimeError(f"BIP39 wordlist must have 2048 words, got {len(BIP39_ENGLISH)}")

    return BIP39_ENGLISH


def generate_mnemonic(strength: int = 256) -> str:
    """
    Generate a BIP-39 mnemonic phrase.
    strength: 128 (12 words), 160 (15), 192 (18), 224 (21), 256 (24 words)
    """
    if strength not in (128, 160, 192, 224, 256):
        raise ValueError("Strength must be 128/160/192/224/256")

    wordlist = _load_wordlist()
    entropy = secrets.token_bytes(strength // 8)
    h = hashlib.sha256(entropy).digest()

    # Convert entropy + checksum bits to binary string
    bits = bin(int.from_bytes(entropy, 'big'))[2:].zfill(strength)
    checksum_bits = bin(int.from_bytes(h, 'big'))[2:].zfill(256)
    cs_len = strength // 32
    bits += checksum_bits[:cs_len]

    # Split into 11-bit groups
    words = []
    for i in range(0, len(bits), 11):
        idx = int(bits[i:i + 11], 2)
        words.append(wordlist[idx])

    return ' '.join(words)


def validate_mnemonic(mnemonic: str) -> bool:
    """Validate a BIP-39 mnemonic phrase."""
    wordlist = _load_wordlist()
    words = mnemonic.strip().split()

    if len(words) not in (12, 15, 18, 21, 24):
        return False

    for word in words:
        if word not in wordlist:
            return False

    # Reconstruct bits
    bits = ''
    for word in words:
        idx = wordlist.index(word)
        bits += bin(idx)[2:].zfill(11)

    # Split entropy and checksum
    cs_len = len(words) // 3
    entropy_bits = bits[:-cs_len]
    checksum_bits = bits[-cs_len:]

    # Verify checksum
    entropy_bytes = int(entropy_bits, 2).to_bytes(len(entropy_bits) // 8, 'big')
    h = hashlib.sha256(entropy_bytes).digest()
    expected_cs = bin(int.from_bytes(h, 'big'))[2:].zfill(256)[:cs_len]

    return checksum_bits == expected_cs


def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """
    Convert a BIP-39 mnemonic to a 512-bit seed using PBKDF2.
    The passphrase provides additional security (BIP-39 standard).
    """
    mnemonic_normalized = unicodedata.normalize("NFKD", mnemonic)
    passphrase_normalized = unicodedata.normalize("NFKD", "mnemonic" + passphrase)

    seed = hashlib.pbkdf2_hmac(
        'sha512',
        mnemonic_normalized.encode('utf-8'),
        passphrase_normalized.encode('utf-8'),
        iterations=2048,
        dklen=64
    )
    return seed
