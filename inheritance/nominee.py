"""
Nominee and Inheritance Management for BITWILL.
Handles pre-signing transactions to nominee addresses and
maintaining duplicate records in the master wallet.
"""

import time
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

from ..core.hd_key import HDKey, derive_path, bip44_path
from ..core.transaction import (
    Transaction, TxInput, TxOutput, btc_to_satoshis, satoshis_to_btc,
    address_to_script_pubkey, sign_full_transaction, p2pkh_script,
    sign_transaction_input, create_script_sig
)
from ..core.crypto_utils import hash160, privkey_to_pubkey
from ..wallet.master_wallet import MasterWallet, ChildWalletInfo, UTXO


@dataclass
class NomineeRecord:
    """A record of a nominee and their inheritance allocation."""
    nominee_name: str
    nominee_address: str
    child_wallet_name: str
    amount_satoshis: int
    pre_signed_tx_hex: Optional[str] = None
    pre_signed_txid: Optional[str] = None
    created_at: float = 0
    status: str = "pending"  # pending, signed, broadcast, confirmed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'NomineeRecord':
        return cls(**d)


@dataclass
class PreSignedTransaction:
    """
    A pre-signed transaction ready for future broadcast.
    Contains both the nominee copy and the master duplicate.
    """
    txid: str
    raw_hex: str
    source_wallet: str  # child wallet name
    source_address: str
    nominee_name: str
    nominee_address: str
    amount_satoshis: int
    fee_satoshis: int
    created_at: float
    # The duplicate stored in master wallet
    master_duplicate_hex: str = ""
    locktime: int = 0
    status: str = "pre_signed"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'PreSignedTransaction':
        return cls(**d)


class InheritanceManager:
    """
    Manages the inheritance workflow:
    1. Create child wallets with nominee designations
    2. Fund child wallets from master
    3. Pre-sign transactions from child wallets to nominee addresses
    4. Store duplicate pre-signed transactions in the master wallet
    """

    def __init__(self, master_wallet: MasterWallet):
        self.master = master_wallet
        self._nominee_records: Dict[str, NomineeRecord] = {}
        self._pre_signed_txs: List[PreSignedTransaction] = []

    def designate_nominee(self, child_wallet_name: str,
                          nominee_name: str,
                          nominee_address: str,
                          amount_btc: float) -> NomineeRecord:
        """
        Designate a nominee for a child wallet.
        The nominee will receive the specified amount when the
        pre-signed transaction is broadcast.
        """
        child = self.master.get_child_wallet(child_wallet_name)

        record = NomineeRecord(
            nominee_name=nominee_name,
            nominee_address=nominee_address,
            child_wallet_name=child_wallet_name,
            amount_satoshis=btc_to_satoshis(amount_btc),
            created_at=time.time(),
            status="pending"
        )

        # Update the child wallet's nominee info
        child.nominee_address = nominee_address
        child.nominee_name = nominee_name

        key = f"{child_wallet_name}:{nominee_name}"
        self._nominee_records[key] = record
        return record

    def create_pre_signed_transaction(
        self,
        child_wallet_name: str,
        fee_btc: float = 0.0001,
        locktime: int = 0
    ) -> PreSignedTransaction:
        """
        Create and sign a transaction from a child wallet to its nominee.
        This transaction can be broadcast in the future to transfer
        the inheritance.

        Also creates a duplicate record stored in the master wallet.
        """
        child_info = self.master.get_child_wallet(child_wallet_name)

        if not child_info.nominee_address:
            raise ValueError(
                f"No nominee designated for wallet '{child_wallet_name}'"
            )

        if child_info.allocated_satoshis == 0:
            raise ValueError(
                f"Child wallet '{child_wallet_name}' has no allocated funds"
            )

        # Get the child wallet's key for signing
        child_key = self.master.get_child_key(child_wallet_name)
        fee_sat = btc_to_satoshis(fee_btc)
        amount_sat = child_info.allocated_satoshis - fee_sat

        if amount_sat <= 0:
            raise ValueError("Insufficient funds after fee deduction")

        # Build the nominee transaction
        nominee_tx = self._build_nominee_tx(
            child_key=child_key,
            child_info=child_info,
            nominee_address=child_info.nominee_address,
            amount_sat=amount_sat,
            fee_sat=fee_sat,
            locktime=locktime
        )

        # Sign the transaction
        signed_tx = sign_full_transaction(
            nominee_tx, [child_key.private_key] * len(nominee_tx.inputs)
        )
        signed_hex = signed_tx.hex()
        txid = signed_tx.txid()

        # Create the master duplicate (same transaction stored separately)
        master_dup_hex = signed_hex  # Exact duplicate

        # Create the pre-signed transaction record
        pre_signed = PreSignedTransaction(
            txid=txid,
            raw_hex=signed_hex,
            source_wallet=child_wallet_name,
            source_address=child_info.address,
            nominee_name=child_info.nominee_name or "Unknown",
            nominee_address=child_info.nominee_address,
            amount_satoshis=amount_sat,
            fee_satoshis=fee_sat,
            created_at=time.time(),
            master_duplicate_hex=master_dup_hex,
            locktime=locktime,
            status="pre_signed"
        )

        self._pre_signed_txs.append(pre_signed)

        # Store duplicate in master wallet
        self.master.store_pre_signed_tx(pre_signed.to_dict())

        # Update nominee record status
        key = f"{child_wallet_name}:{child_info.nominee_name}"
        if key in self._nominee_records:
            self._nominee_records[key].pre_signed_tx_hex = signed_hex
            self._nominee_records[key].pre_signed_txid = txid
            self._nominee_records[key].status = "signed"

        return pre_signed

    def _build_nominee_tx(self, child_key: HDKey, child_info: ChildWalletInfo,
                          nominee_address: str, amount_sat: int,
                          fee_sat: int, locktime: int) -> Transaction:
        """Build a transaction from child wallet to nominee address."""
        tx = Transaction(testnet=self.master.testnet, locktime=locktime)

        # Use child wallet UTXOs or create a synthetic input
        # referencing the distribution transaction
        if child_info.utxos:
            for utxo_data in child_info.utxos:
                utxo = UTXO.from_dict(utxo_data)
                tx_input = TxInput(
                    txid=bytes.fromhex(utxo.txid),
                    vout=utxo.vout,
                    prev_script_pubkey=bytes.fromhex(utxo.script_pubkey),
                    prev_value=utxo.value
                )
                tx.inputs.append(tx_input)
        else:
            # Create a placeholder input representing the allocated funds
            child_pubkey_hash = hash160(bytes.fromhex(child_info.public_key))
            script_pubkey = p2pkh_script(child_pubkey_hash)

            tx_input = TxInput(
                txid=b'\x00' * 32,  # Placeholder - would be actual txid
                vout=0,
                prev_script_pubkey=script_pubkey,
                prev_value=child_info.allocated_satoshis
            )
            tx.inputs.append(tx_input)

        # Output to nominee
        nominee_script = address_to_script_pubkey(nominee_address)
        tx.outputs.append(TxOutput(value=amount_sat, script_pubkey=nominee_script))

        return tx

    def get_pre_signed_transactions(self) -> List[PreSignedTransaction]:
        return list(self._pre_signed_txs)

    def get_nominee_records(self) -> Dict[str, NomineeRecord]:
        return dict(self._nominee_records)

    def get_inheritance_summary(self) -> Dict:
        """Get a summary of all inheritance allocations."""
        summary = {
            'total_nominees': len(self._nominee_records),
            'total_pre_signed': len(self._pre_signed_txs),
            'total_allocated_btc': 0.0,
            'nominees': [],
            'pre_signed_transactions': []
        }

        for key, record in self._nominee_records.items():
            summary['total_allocated_btc'] += satoshis_to_btc(record.amount_satoshis)
            summary['nominees'].append({
                'nominee_name': record.nominee_name,
                'nominee_address': record.nominee_address,
                'child_wallet': record.child_wallet_name,
                'amount_btc': satoshis_to_btc(record.amount_satoshis),
                'status': record.status
            })

        for pst in self._pre_signed_txs:
            summary['pre_signed_transactions'].append({
                'txid': pst.txid,
                'source_wallet': pst.source_wallet,
                'nominee': pst.nominee_name,
                'nominee_address': pst.nominee_address,
                'amount_btc': satoshis_to_btc(pst.amount_satoshis),
                'fee_btc': satoshis_to_btc(pst.fee_satoshis),
                'status': pst.status,
                'has_master_duplicate': bool(pst.master_duplicate_hex)
            })

        return summary

    def save_state(self, password: str) -> None:
        """Save inheritance state to encrypted storage."""
        data = {
            'nominee_records': {
                k: v.to_dict() for k, v in self._nominee_records.items()
            },
            'pre_signed_txs': [pst.to_dict() for pst in self._pre_signed_txs]
        }
        self.master.store.save('inheritance_state', data, password)

    def load_state(self, password: str) -> None:
        """Load inheritance state from encrypted storage."""
        if not self.master.store.exists('inheritance_state'):
            return
        data = self.master.store.load('inheritance_state', password)
        self._nominee_records = {
            k: NomineeRecord.from_dict(v)
            for k, v in data.get('nominee_records', {}).items()
        }
        self._pre_signed_txs = [
            PreSignedTransaction.from_dict(pst)
            for pst in data.get('pre_signed_txs', [])
        ]
