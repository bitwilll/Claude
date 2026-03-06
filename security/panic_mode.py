"""
Panic Mode Security System for BITWILL.

When a user enters the WRONG passphrase/key, instead of showing an error,
the system presents a convincing DECOY wallet with fake balances and
obfuscated transaction history. This protects against coercion attacks
(e.g., "$5 wrench attack") where an adversary forces the user to reveal
their wallet.

Architecture:
- The real wallet uses the correct passphrase to derive keys.
- The decoy wallet uses a DIFFERENT deterministic derivation from the
  wrong passphrase, so it always shows consistent (but fake) data.
- The decoy is indistinguishable from a real low-balance wallet.
"""

import hashlib
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from ..core.crypto_utils import (
    sha256, double_sha256, hmac_sha512, privkey_to_pubkey, pubkey_to_address,
    hash160, private_key_to_wif
)
from ..core.hd_key import HDKey, master_key_from_seed, derive_path, bip44_path
from ..core.mnemonic import mnemonic_to_seed
from ..core.transaction import satoshis_to_btc, btc_to_satoshis


# The panic mode passphrase prefix used to derive decoy wallet
# This creates a distinct key space from the real wallet
DECOY_SALT = b"BITWILL_DECOY_DERIVATION_v1"


@dataclass
class DecoyUTXO:
    """A fake UTXO shown in the decoy wallet."""
    txid: str
    vout: int
    value: int  # satoshis
    address: str
    age_days: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecoyTransaction:
    """A fake transaction in the decoy wallet history."""
    txid: str
    direction: str  # "received" or "sent"
    amount: int  # satoshis
    address: str
    timestamp: float
    confirmations: int

    def to_dict(self) -> dict:
        return asdict(self)


class PanicModeManager:
    """
    Manages the panic/duress mode functionality.

    The system maintains two key spaces:
    1. REAL: Derived from mnemonic + correct passphrase
    2. DECOY: Derived from mnemonic + wrong passphrase (via DECOY_SALT)

    When the wrong passphrase is entered, the decoy wallet is shown with:
    - A small, believable balance (derived deterministically)
    - Fake transaction history
    - Valid-looking but worthless addresses
    - No access to real funds or inheritance data
    """

    def __init__(self, real_passphrase_hash: bytes, testnet: bool = True):
        """
        real_passphrase_hash: SHA256 hash of the correct passphrase.
        This is stored to distinguish real vs. decoy access attempts.
        """
        self._real_pass_hash = real_passphrase_hash
        self.testnet = testnet
        self._decoy_config: Dict = {}
        self._panic_triggered_count = 0
        self._panic_log: List[Dict] = []

    @staticmethod
    def hash_passphrase(passphrase: str) -> bytes:
        """Hash a passphrase for comparison."""
        return sha256(sha256(passphrase.encode('utf-8')))

    def is_panic_passphrase(self, entered_passphrase: str) -> bool:
        """
        Check if the entered passphrase triggers panic mode.
        Returns True if the passphrase is WRONG (triggering decoy).
        """
        entered_hash = self.hash_passphrase(entered_passphrase)
        return entered_hash != self._real_pass_hash

    def generate_decoy_wallet(self, mnemonic: str,
                              wrong_passphrase: str) -> 'DecoyWallet':
        """
        Generate a decoy wallet deterministically from the wrong passphrase.
        The decoy looks like a real wallet but has a small, fake balance.
        """
        # Derive decoy seed using the wrong passphrase + decoy salt
        decoy_input = wrong_passphrase.encode('utf-8') + DECOY_SALT
        decoy_passphrase = hashlib.sha256(decoy_input).hexdigest()

        # Use the same mnemonic but different passphrase creates entirely
        # different keys (BIP-39 feature)
        decoy_seed = mnemonic_to_seed(mnemonic, passphrase=decoy_passphrase)
        decoy_master = master_key_from_seed(decoy_seed, testnet=self.testnet)

        # Log panic trigger (without revealing what was entered)
        self._panic_triggered_count += 1
        self._panic_log.append({
            'timestamp': time.time(),
            'attempt_number': self._panic_triggered_count
        })

        return DecoyWallet(
            master_key=decoy_master,
            wrong_passphrase=wrong_passphrase,
            testnet=self.testnet
        )

    def get_panic_log(self) -> List[Dict]:
        """Get the log of panic mode triggers (for the real owner)."""
        return list(self._panic_log)

    def save_config(self) -> Dict:
        """Export panic mode configuration for storage."""
        return {
            'real_pass_hash': self._real_pass_hash.hex(),
            'panic_count': self._panic_triggered_count,
            'panic_log': self._panic_log
        }

    def load_config(self, data: Dict) -> None:
        """Load panic mode configuration."""
        self._real_pass_hash = bytes.fromhex(data['real_pass_hash'])
        self._panic_triggered_count = data.get('panic_count', 0)
        self._panic_log = data.get('panic_log', [])


class DecoyWallet:
    """
    A convincing fake wallet shown during panic mode.
    All data is deterministically generated from the wrong passphrase,
    so it's consistent across multiple accesses with the same wrong key.
    """

    def __init__(self, master_key: HDKey, wrong_passphrase: str,
                 testnet: bool = True):
        self._master_key = master_key
        self._passphrase = wrong_passphrase
        self.testnet = testnet

        # Generate deterministic decoy data
        self._seed = sha256(wrong_passphrase.encode('utf-8') + DECOY_SALT)
        self._generate_decoy_data()

    def _generate_decoy_data(self) -> None:
        """Generate all fake wallet data deterministically."""
        self._addresses = []
        self._utxos = []
        self._transactions = []

        # Generate 3 addresses
        for i in range(3):
            key = derive_path(self._master_key, bip44_path(
                account=0, change=0, address_index=i, testnet=self.testnet
            ))
            self._addresses.append(key.address)

        # Generate a small, believable balance
        # Deterministic from seed so it's consistent
        seed_int = int.from_bytes(self._seed[:8], 'big')
        base_balance = (seed_int % 50000) + 10000  # 0.0001 - 0.0006 BTC

        # Create fake UTXOs
        fake_txid = sha256(self._seed + b"utxo0").hex()
        self._utxos.append(DecoyUTXO(
            txid=fake_txid,
            vout=0,
            value=base_balance,
            address=self._addresses[0],
            age_days=(seed_int % 90) + 7
        ))

        # Maybe add a second small UTXO
        if seed_int % 3 == 0:
            fake_txid2 = sha256(self._seed + b"utxo1").hex()
            small_amount = (seed_int % 20000) + 5000
            self._utxos.append(DecoyUTXO(
                txid=fake_txid2,
                vout=1,
                value=small_amount,
                address=self._addresses[1],
                age_days=(seed_int % 30) + 1
            ))

        # Generate fake transaction history
        self._generate_fake_history(seed_int)

    def _generate_fake_history(self, seed_int: int) -> None:
        """Generate a believable fake transaction history."""
        now = time.time()
        num_txs = (seed_int % 5) + 2  # 2-6 transactions

        for i in range(num_txs):
            tx_seed = sha256(self._seed + f"tx{i}".encode())
            tx_seed_int = int.from_bytes(tx_seed[:8], 'big')

            is_received = (i % 2 == 0) or (i == 0)
            amount = (tx_seed_int % 100000) + 5000

            days_ago = (num_txs - i) * ((tx_seed_int % 15) + 3)
            timestamp = now - (days_ago * 86400)

            # Generate a fake counterparty address
            fake_addr_key = derive_path(self._master_key, bip44_path(
                account=1, change=0, address_index=i, testnet=self.testnet
            ))

            self._transactions.append(DecoyTransaction(
                txid=tx_seed.hex(),
                direction="received" if is_received else "sent",
                amount=amount,
                address=fake_addr_key.address if not is_received
                        else self._addresses[i % len(self._addresses)],
                timestamp=timestamp,
                confirmations=(tx_seed_int % 5000) + 6
            ))

    @property
    def balance(self) -> int:
        """Total decoy balance in satoshis."""
        return sum(u.value for u in self._utxos)

    @property
    def balance_btc(self) -> float:
        return satoshis_to_btc(self.balance)

    @property
    def primary_address(self) -> str:
        return self._addresses[0] if self._addresses else ""

    def get_addresses(self) -> List[str]:
        return list(self._addresses)

    def get_utxos(self) -> List[DecoyUTXO]:
        return list(self._utxos)

    def get_transaction_history(self) -> List[DecoyTransaction]:
        return sorted(self._transactions,
                      key=lambda t: t.timestamp, reverse=True)

    def get_wallet_info(self) -> Dict:
        """Return wallet info that looks like a real wallet."""
        return {
            'network': 'testnet' if self.testnet else 'mainnet',
            'primary_address': self.primary_address,
            'balance_btc': self.balance_btc,
            'address_count': len(self._addresses),
            'utxo_count': len(self._utxos),
            'transaction_count': len(self._transactions),
            'addresses': self._addresses
        }

    def export_display_data(self) -> Dict:
        """Export all display data for the decoy wallet UI."""
        return {
            'wallet_info': self.get_wallet_info(),
            'utxos': [u.to_dict() for u in self._utxos],
            'transactions': [t.to_dict() for t in self.get_transaction_history()],
            # No child wallets, no inheritance, no pre-signed txs
            'child_wallets': [],
            'inheritance': None
        }
