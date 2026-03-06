"""
Bitcoin transaction construction and signing for BITWILL.
Supports creating, signing, and serializing Bitcoin transactions.
"""

import struct
import hashlib
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from .crypto_utils import (
    double_sha256, sha256, privkey_to_pubkey, bytes_to_int, int_to_bytes,
    SECP256K1_ORDER, SECP256K1_G, ec_multiply, ec_add, modinv,
    hash160, base58check_encode, MAINNET_P2PKH_PREFIX, TESTNET_P2PKH_PREFIX,
    base58check_decode
)

# Sighash types
SIGHASH_ALL = 0x01
SIGHASH_NONE = 0x02
SIGHASH_SINGLE = 0x03
SIGHASH_ANYONECANPAY = 0x80

# Satoshi conversion
SATOSHIS_PER_BTC = 100_000_000


def btc_to_satoshis(btc: float) -> int:
    return int(round(btc * SATOSHIS_PER_BTC))


def satoshis_to_btc(satoshis: int) -> float:
    return satoshis / SATOSHIS_PER_BTC


@dataclass
class TxInput:
    """A transaction input (UTXO reference)."""
    txid: bytes          # 32 bytes, internal byte order (reversed from display)
    vout: int            # Output index
    script_sig: bytes = b''
    sequence: int = 0xFFFFFFFF
    # For signing - the scriptPubKey of the referenced output
    prev_script_pubkey: bytes = b''
    prev_value: int = 0  # Value in satoshis (for signing)

    def serialize(self) -> bytes:
        r = self.txid[::-1]  # txid is stored in internal byte order
        r += struct.pack('<I', self.vout)
        r += encode_varint(len(self.script_sig))
        r += self.script_sig
        r += struct.pack('<I', self.sequence)
        return r


@dataclass
class TxOutput:
    """A transaction output."""
    value: int           # Value in satoshis
    script_pubkey: bytes = b''

    def serialize(self) -> bytes:
        r = struct.pack('<q', self.value)
        r += encode_varint(len(self.script_pubkey))
        r += self.script_pubkey
        return r


@dataclass
class Transaction:
    """A Bitcoin transaction."""
    version: int = 1
    inputs: List[TxInput] = field(default_factory=list)
    outputs: List[TxOutput] = field(default_factory=list)
    locktime: int = 0
    testnet: bool = False

    def serialize(self) -> bytes:
        r = struct.pack('<I', self.version)
        r += encode_varint(len(self.inputs))
        for inp in self.inputs:
            r += inp.serialize()
        r += encode_varint(len(self.outputs))
        for out in self.outputs:
            r += out.serialize()
        r += struct.pack('<I', self.locktime)
        return r

    def txid(self) -> str:
        raw = self.serialize()
        h = double_sha256(raw)
        return h[::-1].hex()

    def hex(self) -> str:
        return self.serialize().hex()

    def size(self) -> int:
        return len(self.serialize())

    def sighash(self, input_index: int, script_code: bytes,
                sighash_type: int = SIGHASH_ALL) -> bytes:
        """
        Compute the signature hash for a given input.
        Uses the legacy sighash algorithm.
        """
        tx_copy = Transaction(
            version=self.version,
            inputs=[],
            outputs=list(self.outputs),
            locktime=self.locktime
        )

        for i, inp in enumerate(self.inputs):
            if i == input_index:
                new_input = TxInput(
                    txid=inp.txid,
                    vout=inp.vout,
                    script_sig=script_code,
                    sequence=inp.sequence
                )
            else:
                new_input = TxInput(
                    txid=inp.txid,
                    vout=inp.vout,
                    script_sig=b'',
                    sequence=inp.sequence if sighash_type == SIGHASH_ALL else 0
                )
            tx_copy.inputs.append(new_input)

        raw = tx_copy.serialize()
        raw += struct.pack('<I', sighash_type)
        return double_sha256(raw)


def encode_varint(n: int) -> bytes:
    if n < 0xFD:
        return struct.pack('B', n)
    elif n <= 0xFFFF:
        return b'\xFD' + struct.pack('<H', n)
    elif n <= 0xFFFFFFFF:
        return b'\xFE' + struct.pack('<I', n)
    else:
        return b'\xFF' + struct.pack('<Q', n)


def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    first = data[offset]
    if first < 0xFD:
        return first, offset + 1
    elif first == 0xFD:
        return struct.unpack('<H', data[offset + 1:offset + 3])[0], offset + 3
    elif first == 0xFE:
        return struct.unpack('<I', data[offset + 1:offset + 5])[0], offset + 5
    else:
        return struct.unpack('<Q', data[offset + 1:offset + 9])[0], offset + 9


# --- Script construction ---

def p2pkh_script(pubkey_hash: bytes) -> bytes:
    """Create a P2PKH scriptPubKey: OP_DUP OP_HASH160 <hash> OP_EQUALVERIFY OP_CHECKSIG"""
    return (b'\x76'     # OP_DUP
            b'\xa9'     # OP_HASH160
            b'\x14'     # Push 20 bytes
            + pubkey_hash +
            b'\x88'     # OP_EQUALVERIFY
            b'\xac')    # OP_CHECKSIG


def address_to_script_pubkey(address: str) -> bytes:
    """Convert a Bitcoin address to its scriptPubKey."""
    version, payload = base58check_decode(address)
    if version in (MAINNET_P2PKH_PREFIX, TESTNET_P2PKH_PREFIX):
        return p2pkh_script(payload)
    raise ValueError(f"Unsupported address version: {version.hex()}")


def create_script_sig(signature: bytes, pubkey: bytes) -> bytes:
    """Create a P2PKH scriptSig."""
    sig_len = len(signature)
    pub_len = len(pubkey)
    return bytes([sig_len]) + signature + bytes([pub_len]) + pubkey


# --- ECDSA Signing ---

def sign_transaction_input(tx: Transaction, input_index: int,
                           private_key: bytes,
                           sighash_type: int = SIGHASH_ALL) -> bytes:
    """
    Sign a transaction input and return the DER-encoded signature with sighash byte.
    """
    script_code = tx.inputs[input_index].prev_script_pubkey
    if not script_code:
        pubkey = privkey_to_pubkey(private_key, compressed=True)
        pubkey_hash = hash160(pubkey)
        script_code = p2pkh_script(pubkey_hash)

    msg_hash = tx.sighash(input_index, script_code, sighash_type)
    signature = ecdsa_sign(private_key, msg_hash)
    return signature + bytes([sighash_type])


def ecdsa_sign(private_key: bytes, msg_hash: bytes) -> bytes:
    """
    Sign a message hash using ECDSA with RFC 6979 deterministic k.
    Returns DER-encoded signature.
    """
    z = bytes_to_int(msg_hash)
    d = bytes_to_int(private_key)
    k = _rfc6979_k(private_key, msg_hash)

    point = ec_multiply(SECP256K1_G, k)
    r = point[0] % SECP256K1_ORDER
    if r == 0:
        raise ValueError("Invalid k value")

    s = (modinv(k, SECP256K1_ORDER) * (z + r * d)) % SECP256K1_ORDER
    if s == 0:
        raise ValueError("Invalid k value")

    # Enforce low-S (BIP-62)
    if s > SECP256K1_ORDER // 2:
        s = SECP256K1_ORDER - s

    return der_encode_signature(r, s)


def _rfc6979_k(private_key: bytes, msg_hash: bytes) -> int:
    """Generate deterministic k value per RFC 6979."""
    import hmac as hmac_mod

    q = SECP256K1_ORDER
    x = private_key
    h1 = msg_hash

    # Step b
    v = b'\x01' * 32
    # Step c
    k = b'\x00' * 32
    # Step d
    k = hmac_mod.new(k, v + b'\x00' + x + h1, hashlib.sha256).digest()
    # Step e
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    # Step f
    k = hmac_mod.new(k, v + b'\x01' + x + h1, hashlib.sha256).digest()
    # Step g
    v = hmac_mod.new(k, v, hashlib.sha256).digest()

    while True:
        v = hmac_mod.new(k, v, hashlib.sha256).digest()
        t = bytes_to_int(v)
        if 1 <= t < q:
            return t
        k = hmac_mod.new(k, v + b'\x00', hashlib.sha256).digest()
        v = hmac_mod.new(k, v, hashlib.sha256).digest()


def der_encode_signature(r: int, s: int) -> bytes:
    """DER-encode an ECDSA signature."""
    def encode_int(n):
        b = int_to_bytes(n).lstrip(b'\x00') or b'\x00'
        if b[0] & 0x80:
            b = b'\x00' + b
        return b'\x02' + bytes([len(b)]) + b

    r_enc = encode_int(r)
    s_enc = encode_int(s)
    return b'\x30' + bytes([len(r_enc) + len(s_enc)]) + r_enc + s_enc


def sign_full_transaction(tx: Transaction, private_keys: List[bytes]) -> Transaction:
    """
    Sign all inputs of a transaction.
    private_keys: list of private keys corresponding to each input.
    """
    for i, privkey in enumerate(private_keys):
        pubkey = privkey_to_pubkey(privkey, compressed=True)
        sig = sign_transaction_input(tx, i, privkey)
        tx.inputs[i].script_sig = create_script_sig(sig, pubkey)
    return tx
