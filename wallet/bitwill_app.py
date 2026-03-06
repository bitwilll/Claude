"""
BITWILL Application Controller.
Orchestrates all wallet, inheritance, and security functionality.
This is the main entry point that ties everything together.
"""

import os
import time
from typing import Dict, List, Optional, Tuple

from ..core.mnemonic import generate_mnemonic, validate_mnemonic, mnemonic_to_seed
from ..core.hd_key import derive_path, bip44_path
from ..core.hd_key import derive_path, bip44_path
from ..core.transaction import (
    Transaction, TxInput, TxOutput, btc_to_satoshis, satoshis_to_btc,
    address_to_script_pubkey, p2pkh_script
)
from ..core.crypto_utils import hash160
from ..storage.encrypted_store import EncryptedStore
from .master_wallet import MasterWallet, ChildWalletInfo, UTXO
from ..inheritance.nominee import InheritanceManager, PreSignedTransaction
from ..security.panic_mode import PanicModeManager, DecoyWallet
from ..network.blockchain import BlockchainAPI, NetworkUTXO, AddressInfo, FeeEstimate


DEFAULT_STORAGE_DIR = os.path.expanduser("~/.bitwill")


class BitWillApp:
    """
    Main BITWILL application.

    Workflow:
    1. Create or restore a master wallet (with mnemonic)
    2. Set up panic mode passphrase
    3. Create child wallets with nominee designations
    4. Fund child wallets from master
    5. Pre-sign inheritance transactions
    6. Store everything encrypted

    On login:
    - Correct passphrase -> Full wallet access
    - Wrong passphrase -> Decoy wallet (panic mode)
    """

    def __init__(self, storage_dir: str = DEFAULT_STORAGE_DIR,
                 testnet: bool = True):
        self.storage_dir = storage_dir
        self.testnet = testnet
        self.store = EncryptedStore(storage_dir)
        self.master_wallet = MasterWallet(self.store, testnet=testnet)
        self.inheritance = InheritanceManager(self.master_wallet)
        self.blockchain = BlockchainAPI(testnet=testnet)
        self.panic_manager: Optional[PanicModeManager] = None
        self._is_initialized = False
        self._is_decoy_mode = False
        self._decoy_wallet: Optional[DecoyWallet] = None
        self._passphrase: str = ""

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def is_decoy_mode(self) -> bool:
        return self._is_decoy_mode

    # --- Wallet Creation & Recovery ---

    def create_wallet(self, password: str, passphrase: str = "",
                      strength: int = 256) -> str:
        """
        Create a new BITWILL wallet.
        password: Encryption password for storage.
        passphrase: BIP-39 passphrase (additional seed entropy).
        Returns: mnemonic phrase (MUST be backed up).
        """
        self._passphrase = password
        mnemonic = self.master_wallet.create_new(passphrase, strength)

        # Set up panic mode
        pass_hash = PanicModeManager.hash_passphrase(password)
        self.panic_manager = PanicModeManager(pass_hash, testnet=self.testnet)

        self._is_initialized = True
        self._save_all(password)
        return mnemonic

    def restore_wallet(self, mnemonic: str, password: str,
                       passphrase: str = "") -> None:
        """Restore a wallet from a mnemonic phrase."""
        self._passphrase = password
        self.master_wallet.restore_from_mnemonic(mnemonic, passphrase)

        pass_hash = PanicModeManager.hash_passphrase(password)
        self.panic_manager = PanicModeManager(pass_hash, testnet=self.testnet)

        self._is_initialized = True
        self._save_all(password)

    def unlock(self, password: str, passphrase: str = "") -> bool:
        """
        Unlock the wallet with a password.
        Returns True if this is the REAL wallet.
        Returns False if panic mode was triggered (decoy shown).

        IMPORTANT: Both cases appear successful to the caller.
        The UI should not distinguish between real and decoy.
        """
        if not self.store.exists('panic_config'):
            raise FileNotFoundError("No wallet found. Create one first.")

        # Load panic config to check passphrase
        try:
            panic_data = self.store.load('panic_config', password)
            # Correct password - load real wallet
            self.panic_manager = PanicModeManager(
                bytes.fromhex(panic_data['real_pass_hash']),
                testnet=self.testnet
            )
            self.panic_manager.load_config(panic_data)
        except Exception:
            # Wrong password for panic_config - try to detect panic mode
            # We need to load panic_config with the REAL password,
            # but we don't have it. Instead, we use a two-layer approach.
            pass

        # Try loading the real wallet
        try:
            self.master_wallet.load(password, passphrase)
            self._passphrase = password
            self._is_initialized = True
            self._is_decoy_mode = False

            # Load inheritance state
            try:
                self.inheritance.load_state(password)
            except (FileNotFoundError, Exception):
                pass

            return True

        except Exception:
            # Wrong password - trigger panic mode
            return self._activate_panic_mode(password)

    def _activate_panic_mode(self, wrong_password: str) -> bool:
        """
        Activate panic mode with a decoy wallet.
        This is triggered when the wrong password is entered.
        """
        # We need the mnemonic to generate a consistent decoy.
        # Since we can't decrypt the real wallet, we derive a
        # deterministic decoy from the wrong password alone.
        from ..core.crypto_utils import sha256

        # Create a deterministic but fake mnemonic-derived seed
        decoy_seed_input = sha256(
            wrong_password.encode('utf-8') + b"BITWILL_PANIC_SEED"
        )
        # Extend to 64 bytes (seed length)
        decoy_seed = decoy_seed_input + sha256(decoy_seed_input + b"extend")
        from ..core.hd_key import master_key_from_seed
        decoy_master = master_key_from_seed(decoy_seed, testnet=self.testnet)

        self._decoy_wallet = DecoyWallet(
            master_key=decoy_master,
            wrong_passphrase=wrong_password,
            testnet=self.testnet
        )
        self._is_decoy_mode = True
        self._is_initialized = True

        return False  # Indicates decoy, but caller shouldn't reveal this

    # --- Child Wallet Management ---

    def create_child_wallet(self, name: str,
                            nominee_address: Optional[str] = None,
                            nominee_name: Optional[str] = None) -> ChildWalletInfo:
        """Create a child wallet under the master."""
        self._ensure_real_wallet()
        child = self.master_wallet.create_child_wallet(
            name, nominee_address, nominee_name
        )
        self._save_all(self._passphrase)
        return child

    def distribute_btc(self, child_name: str, amount_btc: float,
                       fee_btc: float = 0.0001) -> Dict:
        """
        Distribute BTC from master wallet to a child wallet.
        Creates and signs the distribution transaction.
        """
        self._ensure_real_wallet()

        # Create the distribution transaction
        tx = self.master_wallet.distribute_to_child(
            child_name, amount_btc, fee_btc
        )

        # Sign it
        signed_tx = self.master_wallet.sign_transaction(tx)

        # Record the UTXO in the child wallet for future pre-signing
        child = self.master_wallet.get_child_wallet(child_name)
        child_key = self.master_wallet.get_child_key(child_name)
        child_pubkey_hash = hash160(bytes.fromhex(child.public_key))
        script_pubkey = p2pkh_script(child_pubkey_hash)

        child.utxos.append({
            'txid': signed_tx.txid(),
            'vout': 0,
            'value': btc_to_satoshis(amount_btc),
            'script_pubkey': script_pubkey.hex(),
            'address': child.address,
            'confirmed': False
        })

        self._save_all(self._passphrase)

        return {
            'txid': signed_tx.txid(),
            'hex': signed_tx.hex(),
            'amount_btc': amount_btc,
            'fee_btc': fee_btc,
            'child_wallet': child_name,
            'child_address': child.address
        }

    # --- Inheritance / Pre-Signing ---

    def designate_nominee(self, child_wallet_name: str,
                          nominee_name: str,
                          nominee_address: str,
                          amount_btc: float) -> Dict:
        """Designate a nominee for inheritance."""
        self._ensure_real_wallet()
        record = self.inheritance.designate_nominee(
            child_wallet_name, nominee_name, nominee_address, amount_btc
        )
        self._save_all(self._passphrase)
        return record.to_dict()

    def pre_sign_inheritance(self, child_wallet_name: str,
                             fee_btc: float = 0.0001,
                             locktime: int = 0) -> Dict:
        """
        Pre-sign the inheritance transaction for a child wallet.
        Creates a signed transaction to the nominee AND stores
        a duplicate in the master wallet.
        """
        self._ensure_real_wallet()

        pre_signed = self.inheritance.create_pre_signed_transaction(
            child_wallet_name, fee_btc, locktime
        )

        self.inheritance.save_state(self._passphrase)
        self._save_all(self._passphrase)

        return {
            'txid': pre_signed.txid,
            'raw_hex': pre_signed.raw_hex,
            'nominee': pre_signed.nominee_name,
            'nominee_address': pre_signed.nominee_address,
            'amount_btc': satoshis_to_btc(pre_signed.amount_satoshis),
            'fee_btc': satoshis_to_btc(pre_signed.fee_satoshis),
            'master_duplicate_stored': bool(pre_signed.master_duplicate_hex),
            'status': pre_signed.status
        }

    def get_inheritance_summary(self) -> Dict:
        """Get full inheritance summary."""
        if self._is_decoy_mode:
            return {'total_nominees': 0, 'nominees': [],
                    'pre_signed_transactions': []}
        return self.inheritance.get_inheritance_summary()

    # --- Wallet Info ---

    def get_wallet_info(self) -> Dict:
        """Get wallet information (works for both real and decoy)."""
        if self._is_decoy_mode and self._decoy_wallet:
            return self._decoy_wallet.get_wallet_info()
        return self.master_wallet.export_wallet_info()

    def get_balance(self) -> float:
        """Get balance in BTC."""
        if self._is_decoy_mode and self._decoy_wallet:
            return self._decoy_wallet.balance_btc
        return self.master_wallet.balance_btc

    def get_address(self) -> str:
        """Get the primary receiving address."""
        if self._is_decoy_mode and self._decoy_wallet:
            return self._decoy_wallet.primary_address
        return self.master_wallet.address

    def get_new_address(self) -> str:
        """Generate a new receiving address."""
        if self._is_decoy_mode and self._decoy_wallet:
            addrs = self._decoy_wallet.get_addresses()
            return addrs[-1] if addrs else ""
        return self.master_wallet.get_new_address()

    def list_child_wallets(self) -> List[Dict]:
        """List all child wallets."""
        if self._is_decoy_mode:
            return []
        return [
            {
                'name': cw.name,
                'address': cw.address,
                'allocated_btc': satoshis_to_btc(cw.allocated_satoshis),
                'nominee': cw.nominee_name,
                'nominee_address': cw.nominee_address,
                'derivation_path': cw.derivation_path
            }
            for cw in self.master_wallet.list_child_wallets()
        ]

    def get_transaction_history(self) -> List[Dict]:
        """Get transaction history."""
        if self._is_decoy_mode and self._decoy_wallet:
            return [t.to_dict() for t in
                    self._decoy_wallet.get_transaction_history()]
        # Real wallet would fetch from blockchain
        return []

    def add_utxo(self, txid: str, vout: int, value_btc: float,
                 address: Optional[str] = None) -> None:
        """Manually add a UTXO to the master wallet (for testing)."""
        self._ensure_real_wallet()
        addr = address or self.master_wallet.address
        key = derive_path(
            self.master_wallet._master_key,
            bip44_path(account=0, change=0, address_index=0,
                       testnet=self.testnet)
        )
        pubkey_hash = hash160(key.public_key)
        script = p2pkh_script(pubkey_hash)

        self.master_wallet.add_utxo(
            txid=txid,
            vout=vout,
            value_sat=btc_to_satoshis(value_btc),
            script_pubkey=script.hex(),
            address=addr
        )
        self._save_all(self._passphrase)

    # --- Network Integration ---

    def sync_balance(self, address: Optional[str] = None) -> Dict:
        """Fetch live balance from the blockchain."""
        addr = address or self.get_address()
        info = self.blockchain.get_address_info(addr)
        return info.to_dict()

    def sync_utxos(self) -> List[Dict]:
        """Fetch UTXOs from the blockchain and update the wallet."""
        self._ensure_real_wallet()
        addr = self.get_address()
        network_utxos = self.blockchain.get_utxos(addr)

        # Derive the script_pubkey for our address
        key = derive_path(
            self.master_wallet._master_key,
            bip44_path(account=0, change=0, address_index=0,
                       testnet=self.testnet)
        )
        pubkey_hash = hash160(key.public_key)
        script = p2pkh_script(pubkey_hash)

        # Replace local UTXOs with fresh network data
        self.master_wallet._utxos.clear()
        for nu in network_utxos:
            self.master_wallet.add_utxo(
                txid=nu.txid,
                vout=nu.vout,
                value_sat=nu.value,
                script_pubkey=script.hex(),
                address=addr,
            )
        self._save_all(self._passphrase)
        return [nu.to_dict() for nu in network_utxos]

    def broadcast_transaction(self, raw_hex: str) -> str:
        """Broadcast a signed transaction to the network. Returns txid."""
        return self.blockchain.broadcast_transaction(raw_hex)

    def broadcast_pre_signed(self, child_wallet_name: str) -> Dict:
        """Broadcast the pre-signed inheritance TX for a child wallet."""
        self._ensure_real_wallet()
        for pst in self.inheritance.get_pre_signed_transactions():
            if pst.source_wallet == child_wallet_name:
                txid = self.blockchain.broadcast_transaction(pst.raw_hex)
                pst.status = "broadcast"
                self.inheritance.save_state(self._passphrase)
                return {
                    'txid': txid,
                    'nominee': pst.nominee_name,
                    'amount_btc': satoshis_to_btc(pst.amount_satoshis),
                    'status': 'broadcast'
                }
        raise ValueError(
            f"No pre-signed TX found for wallet '{child_wallet_name}'"
        )

    def get_fee_estimates(self) -> Dict:
        """Get current network fee estimates."""
        fees = self.blockchain.get_fee_estimates()
        return fees.to_dict()

    def get_network_tx_history(self, address: Optional[str] = None) -> List[Dict]:
        """Fetch transaction history from the network."""
        addr = address or self.get_address()
        return self.blockchain.get_address_transactions(addr)

    def get_tx_status(self, txid: str) -> Dict:
        """Check the confirmation status of a transaction."""
        return self.blockchain.get_transaction_status(txid)

    def check_network(self) -> Dict:
        """Check network connectivity and return status."""
        connected = self.blockchain.check_connectivity()
        result = {
            'connected': connected,
            'network': 'testnet' if self.testnet else 'mainnet',
        }
        if connected:
            try:
                result['block_height'] = self.blockchain.get_block_height()
            except Exception:
                pass
        return result

    def ping_network(self) -> Dict:
        """Ping blockchain endpoints with latency info."""
        return self.blockchain.ping()

    def switch_network(self, testnet: bool) -> None:
        """Switch between testnet and mainnet."""
        self.testnet = testnet
        self.blockchain = BlockchainAPI(testnet=testnet)

    # --- Panic Mode ---

    def get_panic_log(self) -> List[Dict]:
        """Get the panic mode trigger log (only visible in real wallet)."""
        if self._is_decoy_mode or not self.panic_manager:
            return []
        return self.panic_manager.get_panic_log()

    # --- Internal ---

    def _ensure_real_wallet(self) -> None:
        if self._is_decoy_mode:
            raise PermissionError("Operation not available")
        if not self._is_initialized:
            raise ValueError("Wallet not initialized")

    def _save_all(self, password: str) -> None:
        """Save all wallet state."""
        self.master_wallet.save(password)
        if self.panic_manager:
            self.store.save('panic_config',
                            self.panic_manager.save_config(), password)

    def wallet_exists(self) -> bool:
        """Check if a wallet already exists in storage."""
        return self.store.exists('master_wallet')
