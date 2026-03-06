"""
Master Wallet for BITWILL.
The master wallet is the root of the HD key hierarchy.
It manages child wallets, UTXO tracking, and denomination distribution.
"""

import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from ..core.mnemonic import generate_mnemonic, validate_mnemonic, mnemonic_to_seed
from ..core.hd_key import (
    HDKey, master_key_from_seed, derive_child_key, derive_path,
    bip44_path, HARDENED_OFFSET
)
from ..core.transaction import (
    Transaction, TxInput, TxOutput, btc_to_satoshis, satoshis_to_btc,
    address_to_script_pubkey, sign_full_transaction, p2pkh_script
)
from ..core.crypto_utils import hash160, pubkey_to_address
from ..storage.encrypted_store import EncryptedStore


@dataclass
class UTXO:
    """Unspent Transaction Output."""
    txid: str
    vout: int
    value: int  # satoshis
    script_pubkey: str  # hex
    address: str
    confirmed: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'UTXO':
        return cls(**d)


@dataclass
class ChildWalletInfo:
    """Metadata about a child wallet."""
    name: str
    derivation_path: str
    address: str
    public_key: str  # hex
    created_at: float
    allocated_satoshis: int = 0
    nominee_address: Optional[str] = None
    nominee_name: Optional[str] = None
    utxos: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ChildWalletInfo':
        return cls(**d)


class MasterWallet:
    """
    The master wallet controls the HD key hierarchy.
    It can create child wallets, distribute BTC, and manage inheritance.
    """

    def __init__(self, store: EncryptedStore, testnet: bool = True):
        self.store = store
        self.testnet = testnet
        self._master_key: Optional[HDKey] = None
        self._mnemonic: Optional[str] = None
        self._child_wallets: Dict[str, ChildWalletInfo] = {}
        self._utxos: List[UTXO] = []
        self._next_child_index: int = 0
        self._next_address_index: int = 0
        self._pre_signed_txs: List[Dict] = []
        self._created_at: float = 0

    def switch_network(self, testnet: bool) -> None:
        """Switch between testnet and mainnet.
        Re-derives the master key so all addresses use the correct network prefix.
        Mainnet: BIP-44 coin_type=0, address prefix 0x00 (starts with '1')
        Testnet: BIP-44 coin_type=1, address prefix 0x6F (starts with 'm'/'n')
        """
        self.testnet = testnet
        if self._master_key:
            self._master_key.testnet = testnet

    @property
    def address(self) -> Optional[str]:
        if self._master_key:
            # Use first receiving address
            # Mainnet: m/44'/0'/0'/0/0 -> address starts with '1'
            # Testnet: m/44'/1'/0'/0/0 -> address starts with 'm' or 'n'
            key = derive_path(self._master_key, bip44_path(
                account=0, change=0, address_index=0, testnet=self.testnet
            ))
            return key.address
        return None

    @property
    def balance(self) -> int:
        """Total balance in satoshis."""
        return sum(u.value for u in self._utxos)

    @property
    def balance_btc(self) -> float:
        return satoshis_to_btc(self.balance)

    def create_new(self, passphrase: str = "", strength: int = 256) -> str:
        """
        Create a new master wallet with a fresh mnemonic.
        Returns the mnemonic phrase (MUST be backed up by user).
        """
        self._mnemonic = generate_mnemonic(strength)
        seed = mnemonic_to_seed(self._mnemonic, passphrase)
        self._master_key = master_key_from_seed(seed, testnet=self.testnet)
        self._created_at = time.time()
        self._child_wallets = {}
        self._utxos = []
        self._next_child_index = 0
        self._next_address_index = 1
        self._pre_signed_txs = []
        return self._mnemonic

    def restore_from_mnemonic(self, mnemonic: str, passphrase: str = "") -> None:
        """Restore a master wallet from an existing mnemonic."""
        if not validate_mnemonic(mnemonic):
            raise ValueError("Invalid mnemonic phrase")
        self._mnemonic = mnemonic
        seed = mnemonic_to_seed(mnemonic, passphrase)
        self._master_key = master_key_from_seed(seed, testnet=self.testnet)
        self._created_at = time.time()
        self._child_wallets = {}
        self._utxos = []
        self._next_child_index = 0
        self._next_address_index = 1
        self._pre_signed_txs = []

    def create_child_wallet(self, name: str,
                            nominee_address: Optional[str] = None,
                            nominee_name: Optional[str] = None) -> ChildWalletInfo:
        """
        Create a new child wallet derived from the master key.
        Uses BIP-44 path: m/44'/0'/account'/0/0
        Each child wallet gets its own account index.
        """
        if not self._master_key:
            raise ValueError("Master wallet not initialized")

        if name in self._child_wallets:
            raise ValueError(f"Child wallet '{name}' already exists")

        account_index = self._next_child_index
        self._next_child_index += 1

        path = bip44_path(
            account=account_index,
            change=0,
            address_index=0,
            testnet=self.testnet
        )

        child_key = derive_path(self._master_key, path)

        child_info = ChildWalletInfo(
            name=name,
            derivation_path=path,
            address=child_key.address,
            public_key=child_key.public_key.hex(),
            created_at=time.time(),
            nominee_address=nominee_address,
            nominee_name=nominee_name
        )

        self._child_wallets[name] = child_info
        return child_info

    def get_child_key(self, name: str) -> HDKey:
        """Get the HD key for a child wallet."""
        if name not in self._child_wallets:
            raise ValueError(f"Child wallet '{name}' not found")
        child = self._child_wallets[name]
        return derive_path(self._master_key, child.derivation_path)

    def distribute_to_child(self, child_name: str, amount_btc: float,
                            fee_btc: float = 0.0001) -> Transaction:
        """
        Create a transaction to distribute BTC from master to a child wallet.
        Returns the constructed (unsigned) transaction.
        """
        if child_name not in self._child_wallets:
            raise ValueError(f"Child wallet '{child_name}' not found")

        child = self._child_wallets[child_name]
        amount_sat = btc_to_satoshis(amount_btc)
        fee_sat = btc_to_satoshis(fee_btc)
        total_needed = amount_sat + fee_sat

        # Select UTXOs (simple greedy)
        selected_utxos, selected_total = self._select_utxos(total_needed)
        if selected_total < total_needed:
            raise ValueError(
                f"Insufficient funds. Need {satoshis_to_btc(total_needed)} BTC, "
                f"have {satoshis_to_btc(selected_total)} BTC"
            )

        # Build transaction
        tx = Transaction(testnet=self.testnet)

        # Add inputs
        for utxo in selected_utxos:
            tx_input = TxInput(
                txid=bytes.fromhex(utxo.txid),
                vout=utxo.vout,
                prev_script_pubkey=bytes.fromhex(utxo.script_pubkey),
                prev_value=utxo.value
            )
            tx.inputs.append(tx_input)

        # Output to child wallet
        child_script = address_to_script_pubkey(child.address)
        tx.outputs.append(TxOutput(value=amount_sat, script_pubkey=child_script))

        # Change output back to master
        change = selected_total - total_needed
        if change > 546:  # Dust threshold
            master_script = address_to_script_pubkey(self.address)
            tx.outputs.append(TxOutput(value=change, script_pubkey=master_script))

        # Update child allocated amount
        child.allocated_satoshis += amount_sat

        return tx

    def sign_transaction(self, tx: Transaction,
                         account: int = 0) -> Transaction:
        """Sign a transaction using the master wallet's keys."""
        # Derive the signing key
        key = derive_path(self._master_key, bip44_path(
            account=account, change=0, address_index=0, testnet=self.testnet
        ))

        private_keys = [key.private_key] * len(tx.inputs)
        return sign_full_transaction(tx, private_keys)

    def _select_utxos(self, target: int) -> Tuple[List[UTXO], int]:
        """Select UTXOs to meet target amount (simple greedy algorithm)."""
        sorted_utxos = sorted(self._utxos, key=lambda u: u.value, reverse=True)
        selected = []
        total = 0
        for utxo in sorted_utxos:
            selected.append(utxo)
            total += utxo.value
            if total >= target:
                break
        return selected, total

    def add_utxo(self, txid: str, vout: int, value_sat: int,
                 script_pubkey: str, address: str) -> None:
        """Manually add a UTXO (for testing or manual import)."""
        utxo = UTXO(
            txid=txid, vout=vout, value=value_sat,
            script_pubkey=script_pubkey, address=address
        )
        self._utxos.append(utxo)

    def get_new_address(self) -> str:
        """Generate a new receiving address from the master key."""
        idx = self._next_address_index
        self._next_address_index += 1
        key = derive_path(self._master_key, bip44_path(
            account=0, change=0, address_index=idx, testnet=self.testnet
        ))
        return key.address

    def list_child_wallets(self) -> List[ChildWalletInfo]:
        return list(self._child_wallets.values())

    def get_child_wallet(self, name: str) -> ChildWalletInfo:
        if name not in self._child_wallets:
            raise ValueError(f"Child wallet '{name}' not found")
        return self._child_wallets[name]

    def save(self, password: str) -> None:
        """Encrypt and save the wallet state."""
        data = {
            'version': 1,
            'testnet': self.testnet,
            'mnemonic': self._mnemonic,
            'created_at': self._created_at,
            'next_child_index': self._next_child_index,
            'next_address_index': self._next_address_index,
            'child_wallets': {
                name: cw.to_dict() for name, cw in self._child_wallets.items()
            },
            'utxos': [u.to_dict() for u in self._utxos],
            'pre_signed_txs': self._pre_signed_txs
        }
        self.store.save('master_wallet', data, password)

    def load(self, password: str, passphrase: str = "") -> None:
        """Load and decrypt the wallet state."""
        data = self.store.load('master_wallet', password)

        self.testnet = data.get('testnet', True)
        self._mnemonic = data['mnemonic']
        self._created_at = data.get('created_at', 0)
        self._next_child_index = data.get('next_child_index', 0)
        self._next_address_index = data.get('next_address_index', 1)

        # Restore master key from mnemonic
        seed = mnemonic_to_seed(self._mnemonic, passphrase)
        self._master_key = master_key_from_seed(seed, testnet=self.testnet)

        # Restore child wallets
        self._child_wallets = {}
        for name, cw_data in data.get('child_wallets', {}).items():
            self._child_wallets[name] = ChildWalletInfo.from_dict(cw_data)

        # Restore UTXOs
        self._utxos = [UTXO.from_dict(u) for u in data.get('utxos', [])]

        # Restore pre-signed txs
        self._pre_signed_txs = data.get('pre_signed_txs', [])

    def store_pre_signed_tx(self, tx_data: Dict) -> None:
        """Store a pre-signed transaction in the wallet."""
        self._pre_signed_txs.append(tx_data)

    def get_pre_signed_txs(self) -> List[Dict]:
        return list(self._pre_signed_txs)

    def export_wallet_info(self) -> Dict:
        """Export non-sensitive wallet information."""
        return {
            'network': 'testnet' if self.testnet else 'mainnet',
            'master_address': self.address,
            'balance_btc': self.balance_btc,
            'child_wallets': [
                {
                    'name': cw.name,
                    'address': cw.address,
                    'allocated_btc': satoshis_to_btc(cw.allocated_satoshis),
                    'nominee': cw.nominee_name,
                    'nominee_address': cw.nominee_address
                }
                for cw in self._child_wallets.values()
            ],
            'pre_signed_tx_count': len(self._pre_signed_txs),
            'created_at': self._created_at
        }
