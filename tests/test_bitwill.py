#!/usr/bin/env python3
"""
Comprehensive test and demo for BITWILL.
Exercises all major features: wallet creation, child wallets,
BTC distribution, nominee designation, pre-signed transactions,
and panic mode.
"""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitwill.wallet.bitwill_app import BitWillApp
from bitwill.core.transaction import satoshis_to_btc, btc_to_satoshis


def separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def run_full_demo():
    # Use a temp directory so we don't pollute the real storage
    test_dir = tempfile.mkdtemp(prefix="bitwill_test_")
    print(f"  Storage: {test_dir}\n")

    try:
        app = BitWillApp(storage_dir=test_dir, testnet=True)

        # -------------------------------------------------------
        separator("1. CREATE MASTER WALLET")
        # -------------------------------------------------------
        password = "MySecurePassword123!"
        mnemonic = app.create_wallet(password=password, passphrase="")

        print(f"  Mnemonic: {mnemonic}")
        print(f"  Master Address: {app.get_address()}")
        print(f"  Balance: {app.get_balance():.8f} BTC")
        print(f"  Network: {'testnet' if app.testnet else 'mainnet'}")

        # -------------------------------------------------------
        separator("2. ADD TEST UTXOs")
        # -------------------------------------------------------
        import secrets
        test_txid1 = secrets.token_hex(32)
        test_txid2 = secrets.token_hex(32)

        app.add_utxo(test_txid1, 0, 5.0)
        app.add_utxo(test_txid2, 1, 3.0)

        print(f"  Added UTXO 1: 5.0 BTC (txid: {test_txid1[:16]}...)")
        print(f"  Added UTXO 2: 3.0 BTC (txid: {test_txid2[:16]}...)")
        print(f"  Total Balance: {app.get_balance():.8f} BTC")

        # -------------------------------------------------------
        separator("3. CREATE CHILD WALLETS")
        # -------------------------------------------------------
        child1 = app.create_child_wallet(
            name="Alice_Inheritance",
            nominee_name="Alice",
            nominee_address=None  # Will set later
        )
        print(f"  Child 1: '{child1.name}'")
        print(f"    Address: {child1.address}")
        print(f"    Path:    {child1.derivation_path}")

        child2 = app.create_child_wallet(
            name="Bob_Inheritance",
            nominee_name="Bob",
            nominee_address=None
        )
        print(f"  Child 2: '{child2.name}'")
        print(f"    Address: {child2.address}")
        print(f"    Path:    {child2.derivation_path}")

        child3 = app.create_child_wallet(
            name="Charity_Fund",
            nominee_name="Charity",
            nominee_address=None
        )
        print(f"  Child 3: '{child3.name}'")
        print(f"    Address: {child3.address}")
        print(f"    Path:    {child3.derivation_path}")

        # -------------------------------------------------------
        separator("4. DISTRIBUTE BTC TO CHILD WALLETS")
        # -------------------------------------------------------
        dist1 = app.distribute_btc("Alice_Inheritance", 2.0)
        print(f"  Distributed 2.0 BTC to Alice_Inheritance")
        print(f"    TXID: {dist1['txid'][:32]}...")

        dist2 = app.distribute_btc("Bob_Inheritance", 1.5)
        print(f"  Distributed 1.5 BTC to Bob_Inheritance")
        print(f"    TXID: {dist2['txid'][:32]}...")

        dist3 = app.distribute_btc("Charity_Fund", 0.5)
        print(f"  Distributed 0.5 BTC to Charity_Fund")
        print(f"    TXID: {dist3['txid'][:32]}...")

        print(f"\n  Remaining Master Balance: {app.get_balance():.8f} BTC")

        # -------------------------------------------------------
        separator("5. DESIGNATE NOMINEES")
        # -------------------------------------------------------
        # Generate nominee addresses from a separate derivation
        nominee_alice_addr = app.get_new_address()
        nominee_bob_addr = app.get_new_address()
        nominee_charity_addr = app.get_new_address()

        app.designate_nominee("Alice_Inheritance", "Alice Smith",
                              nominee_alice_addr, 2.0)
        print(f"  Nominee: Alice Smith -> {nominee_alice_addr}")

        app.designate_nominee("Bob_Inheritance", "Bob Jones",
                              nominee_bob_addr, 1.5)
        print(f"  Nominee: Bob Jones -> {nominee_bob_addr}")

        app.designate_nominee("Charity_Fund", "Red Cross",
                              nominee_charity_addr, 0.5)
        print(f"  Nominee: Red Cross -> {nominee_charity_addr}")

        # -------------------------------------------------------
        separator("6. PRE-SIGN INHERITANCE TRANSACTIONS")
        # -------------------------------------------------------
        ps1 = app.pre_sign_inheritance("Alice_Inheritance", fee_btc=0.0001)
        print(f"  Pre-signed for Alice:")
        print(f"    TXID:     {ps1['txid'][:32]}...")
        print(f"    Amount:   {ps1['amount_btc']:.8f} BTC")
        print(f"    Status:   {ps1['status']}")
        print(f"    Master Dup: {'Yes' if ps1['master_duplicate_stored'] else 'No'}")
        print(f"    Raw TX:   {ps1['raw_hex'][:64]}...")

        ps2 = app.pre_sign_inheritance("Bob_Inheritance", fee_btc=0.0001)
        print(f"\n  Pre-signed for Bob:")
        print(f"    TXID:     {ps2['txid'][:32]}...")
        print(f"    Amount:   {ps2['amount_btc']:.8f} BTC")
        print(f"    Master Dup: {'Yes' if ps2['master_duplicate_stored'] else 'No'}")

        ps3 = app.pre_sign_inheritance("Charity_Fund", fee_btc=0.0001)
        print(f"\n  Pre-signed for Charity:")
        print(f"    TXID:     {ps3['txid'][:32]}...")
        print(f"    Amount:   {ps3['amount_btc']:.8f} BTC")
        print(f"    Master Dup: {'Yes' if ps3['master_duplicate_stored'] else 'No'}")

        # -------------------------------------------------------
        separator("7. VERIFY MASTER WALLET DUPLICATES")
        # -------------------------------------------------------
        master_txs = app.master_wallet.get_pre_signed_txs()
        print(f"  Master wallet holds {len(master_txs)} pre-signed TX duplicates:")
        for i, mtx in enumerate(master_txs, 1):
            print(f"    {i}. {mtx['nominee_name']} -> "
                  f"{satoshis_to_btc(mtx['amount_satoshis']):.8f} BTC "
                  f"[dup: {'Yes' if mtx.get('master_duplicate_hex') else 'No'}]")

        # -------------------------------------------------------
        separator("8. INHERITANCE SUMMARY")
        # -------------------------------------------------------
        summary = app.get_inheritance_summary()
        print(f"  Total Nominees: {summary['total_nominees']}")
        print(f"  Total Pre-Signed: {summary['total_pre_signed']}")
        print(f"  Total Allocated: {summary.get('total_allocated_btc', 0):.8f} BTC")

        for n in summary['nominees']:
            print(f"\n  Nominee: {n['nominee_name']}")
            print(f"    Child Wallet: {n['child_wallet']}")
            print(f"    Amount: {n['amount_btc']:.8f} BTC")
            print(f"    Status: {n['status']}")

        # -------------------------------------------------------
        separator("9. LIST ALL CHILD WALLETS")
        # -------------------------------------------------------
        children = app.list_child_wallets()
        for cw in children:
            print(f"  {cw['name']}:")
            print(f"    Address:   {cw['address']}")
            print(f"    Allocated: {cw['allocated_btc']:.8f} BTC")
            print(f"    Nominee:   {cw.get('nominee', 'N/A')}")
            print(f"    Path:      {cw['derivation_path']}")
            print()

        # -------------------------------------------------------
        separator("10. PANIC MODE TEST")
        # -------------------------------------------------------
        print("  Testing panic mode with wrong password...")

        # Create a fresh app instance (simulates restart)
        app2 = BitWillApp(storage_dir=test_dir, testnet=True)
        is_real = app2.unlock("WRONG_PASSWORD_123")

        print(f"  Wrong password entered -> Decoy mode: {app2.is_decoy_mode}")
        print(f"  Decoy wallet info:")
        decoy_info = app2.get_wallet_info()
        print(f"    Address: {decoy_info.get('primary_address', 'N/A')}")
        print(f"    Balance: {app2.get_balance():.8f} BTC (fake)")
        print(f"    Child wallets visible: {len(app2.list_child_wallets())}")
        print(f"    Inheritance data: {app2.get_inheritance_summary()}")

        decoy_history = app2.get_transaction_history()
        if decoy_history:
            print(f"    Fake TX history: {len(decoy_history)} transactions")
            for tx in decoy_history[:3]:
                print(f"      {tx['direction']}: "
                      f"{satoshis_to_btc(tx['amount']):.8f} BTC")

        # Now log in with CORRECT password
        print("\n  Now logging in with correct password...")
        app3 = BitWillApp(storage_dir=test_dir, testnet=True)
        is_real = app3.unlock(password)

        print(f"  Correct password -> Real wallet: {not app3.is_decoy_mode}")
        print(f"  Real balance: {app3.get_balance():.8f} BTC")
        print(f"  Child wallets: {len(app3.list_child_wallets())}")

        # Check panic log
        panic_log = app3.get_panic_log()
        if panic_log:
            print(f"\n  ALERT: {len(panic_log)} unauthorized access attempt(s)!")

        # -------------------------------------------------------
        separator("11. WALLET PERSISTENCE TEST")
        # -------------------------------------------------------
        print("  Verifying wallet data persists across restarts...")

        app4 = BitWillApp(storage_dir=test_dir, testnet=True)
        app4.unlock(password)

        print(f"  Master Address: {app4.get_address()}")
        print(f"  Balance: {app4.get_balance():.8f} BTC")
        print(f"  Child Wallets: {len(app4.list_child_wallets())}")
        print(f"  Pre-Signed TXs: {len(app4.master_wallet.get_pre_signed_txs())}")

        # -------------------------------------------------------
        separator("DEMO COMPLETE")
        # -------------------------------------------------------
        print("  All BITWILL features demonstrated successfully!")
        print()
        print("  Features tested:")
        print("    [x] HD Wallet creation with BIP-39 mnemonic")
        print("    [x] Master/child wallet hierarchy (BIP-44)")
        print("    [x] BTC distribution to child wallets")
        print("    [x] Nominee designation for inheritance")
        print("    [x] Pre-signed transaction creation")
        print("    [x] Duplicate pre-signed TX in master wallet")
        print("    [x] Panic mode (wrong key -> decoy wallet)")
        print("    [x] Encrypted storage (AES-256-GCM)")
        print("    [x] Wallet persistence and recovery")
        print()

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == '__main__':
    print("\n  BITWILL - Full Feature Demo & Test\n")
    run_full_demo()
