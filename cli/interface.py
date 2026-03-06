"""
CLI Interface for BITWILL.
Rich terminal UI for interacting with the wallet.
"""

import os
import sys
import getpass
import time
from typing import Optional

from ..wallet.bitwill_app import BitWillApp
from ..core.transaction import satoshis_to_btc


# ANSI color codes (no external dependency needed)
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def c(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


BANNER = f"""
{Colors.BOLD}{Colors.CYAN}
  ____  ___ _______        _____ _     _
 | __ )|_ _|_   _\\ \\      / /_ _| |   | |
 |  _ \\ | |  | |  \\ \\ /\\ / / | || |   | |
 | |_) || |  | |   \\ V  V /  | || |___| |___
 |____/|___| |_|    \\_/\\_/  |___|_____|_____|
{Colors.RESET}
{Colors.DIM} Blockchain Inheritance & Will Security System{Colors.RESET}
{Colors.DIM} Secure your Bitcoin legacy{Colors.RESET}
"""


class BitWillCLI:
    """Command-line interface for BITWILL."""

    def __init__(self, storage_dir: Optional[str] = None, testnet: bool = True):
        self.storage_dir = storage_dir or os.path.expanduser("~/.bitwill")
        self.app = BitWillApp(storage_dir=self.storage_dir, testnet=testnet)
        self.running = True

    def start(self) -> None:
        print(BANNER)
        self._network_selection()
        if self.app.wallet_exists():
            self._unlock_flow()
        else:
            self._welcome_flow()

        if self.app.is_initialized:
            self._main_menu()

    def _network_selection(self) -> None:
        """Let the user choose between testnet and mainnet at startup."""
        print(c("  === Network Selection ===\n", Colors.BOLD))
        print(f"  1. {c('Testnet', Colors.GREEN)}  (default - safe for testing)")
        print(f"  2. {c('Mainnet', Colors.RED)}  (real Bitcoin - use with caution)")
        print(f"  3. {c('Ping Servers', Colors.CYAN)}  (test connectivity before choosing)\n")

        choice = input(c("  Select network [1]: ", Colors.CYAN)).strip()

        if choice == '3':
            self._ping_both_networks()
            # Ask again after ping
            print()
            print(f"  1. {c('Testnet', Colors.GREEN)}")
            print(f"  2. {c('Mainnet', Colors.RED)}\n")
            choice = input(c("  Select network [1]: ", Colors.CYAN)).strip()

        if choice == '2':
            self.app.switch_network(testnet=False)
            print(c("\n  Network set to MAINNET (real Bitcoin)", Colors.RED))
            print(c("  WARNING: Transactions on mainnet use real BTC!\n", Colors.YELLOW))
        else:
            self.app.switch_network(testnet=True)
            print(c("\n  Network set to TESTNET\n", Colors.GREEN))

    def _ping_both_networks(self) -> None:
        """Ping both testnet and mainnet endpoints."""
        from ..network.blockchain import BlockchainAPI
        print(c("\n  Pinging blockchain servers...\n", Colors.YELLOW))

        for net_label, is_testnet in [("TESTNET", True), ("MAINNET", False)]:
            api = BlockchainAPI(testnet=is_testnet)
            result = api.ping()
            net_color = Colors.GREEN if net_label == "TESTNET" else Colors.RED
            print(f"  {c(f'--- {net_label} ---', net_color)}")
            for ep in result['endpoints']:
                if ep['reachable']:
                    print(f"    {c('OK', Colors.GREEN)}  {ep['url']}")
                    print(f"         Latency: {c(f\"{ep['latency_ms']}ms\", Colors.CYAN)}  "
                          f"Block: {c(str(ep['block_height']), Colors.CYAN)}")
                else:
                    print(f"    {c('FAIL', Colors.RED)}  {ep['url']}")
            print()

    def _welcome_flow(self) -> None:
        print(c("\n  Welcome to BITWILL!", Colors.BOLD))
        print(c("  No wallet found. Let's set one up.\n", Colors.DIM))
        print("  1. Create a new wallet")
        print("  2. Restore from mnemonic")
        print("  3. Exit\n")

        choice = input(c("  Select option: ", Colors.CYAN)).strip()

        if choice == '1':
            self._create_wallet()
        elif choice == '2':
            self._restore_wallet()
        else:
            self.running = False

    def _create_wallet(self) -> None:
        print(c("\n  === Create New Wallet ===\n", Colors.BOLD))

        password = getpass.getpass(c("  Enter encryption password: ", Colors.CYAN))
        confirm = getpass.getpass(c("  Confirm password: ", Colors.CYAN))

        if password != confirm:
            print(c("  Passwords don't match!", Colors.RED))
            return

        if len(password) < 8:
            print(c("  Password must be at least 8 characters!", Colors.RED))
            return

        passphrase = getpass.getpass(
            c("  BIP-39 passphrase (optional, press Enter to skip): ",
              Colors.CYAN)
        )

        print(c("\n  Generating wallet...", Colors.YELLOW))
        mnemonic = self.app.create_wallet(password, passphrase)

        print(c("\n  IMPORTANT: Write down your recovery phrase!", Colors.RED))
        print(c("  " + "=" * 60, Colors.RED))
        print()
        words = mnemonic.split()
        for i in range(0, len(words), 4):
            line = "  "
            for j in range(4):
                if i + j < len(words):
                    line += f"  {i + j + 1:2d}. {words[i + j]:<14s}"
            print(c(line, Colors.YELLOW))
        print()
        print(c("  " + "=" * 60, Colors.RED))
        print(c("  Store this safely. It's the ONLY way to recover your wallet.", Colors.RED))
        print(c("  Anyone with this phrase can access your funds.\n", Colors.RED))

        input(c("  Press Enter after you've saved your recovery phrase...", Colors.DIM))
        print(c("  Wallet created successfully!", Colors.GREEN))

    def _restore_wallet(self) -> None:
        print(c("\n  === Restore Wallet ===\n", Colors.BOLD))

        mnemonic = input(c("  Enter your 12/24 word recovery phrase:\n  ", Colors.CYAN)).strip()
        password = getpass.getpass(c("  Enter encryption password: ", Colors.CYAN))
        passphrase = getpass.getpass(
            c("  BIP-39 passphrase (press Enter if none): ", Colors.CYAN)
        )

        try:
            self.app.restore_wallet(mnemonic, password, passphrase)
            print(c("  Wallet restored successfully!", Colors.GREEN))
        except ValueError as e:
            print(c(f"  Error: {e}", Colors.RED))

    def _unlock_flow(self) -> None:
        print(c("\n  Existing wallet found. Enter your password to unlock.\n", Colors.DIM))
        password = getpass.getpass(c("  Password: ", Colors.CYAN))

        is_real = self.app.unlock(password)

        if is_real:
            print(c("  Wallet unlocked.", Colors.GREEN))
            # Check if panic mode was triggered while away
            panic_log = self.app.get_panic_log()
            if panic_log:
                print(c(f"\n  WARNING: {len(panic_log)} unauthorized access "
                        f"attempt(s) detected!", Colors.RED))
                for entry in panic_log[-3:]:  # Show last 3
                    ts = time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(entry['timestamp']))
                    print(c(f"    - Attempt #{entry['attempt_number']} at {ts}",
                            Colors.YELLOW))
                print()
        else:
            # Decoy mode - show wallet as normal (no indication of panic)
            print(c("  Wallet unlocked.", Colors.GREEN))

    def _main_menu(self) -> None:
        while self.running:
            print(c("\n  === BITWILL Main Menu ===\n", Colors.BOLD))
            print(f"  Network: {c('TESTNET' if self.app.testnet else 'MAINNET', Colors.YELLOW)}")
            print(f"  Balance: {c(f'{self.app.get_balance():.8f} BTC', Colors.GREEN)}")
            print(f"  Address: {c(self.app.get_address(), Colors.CYAN)}")
            print()
            print("  1.  Wallet Info")
            print("  2.  Generate New Address")
            print("  3.  Create Child Wallet")
            print("  4.  List Child Wallets")
            print("  5.  Distribute BTC to Child Wallet")
            print("  6.  Designate Nominee")
            print("  7.  Pre-Sign Inheritance Transaction")
            print("  8.  View Inheritance Summary")
            print("  9.  Add UTXO (Testing)")
            print("  10. View Pre-Signed Transactions")
            print("  11. Transaction History")
            print("  12. Ping Network")
            print("  13. Switch Network (Testnet/Mainnet)")
            print("  0.  Exit\n")

            choice = input(c("  Select option: ", Colors.CYAN)).strip()

            actions = {
                '1': self._show_wallet_info,
                '2': self._generate_address,
                '3': self._create_child_wallet,
                '4': self._list_child_wallets,
                '5': self._distribute_btc,
                '6': self._designate_nominee,
                '7': self._pre_sign_inheritance,
                '8': self._show_inheritance_summary,
                '9': self._add_utxo,
                '10': self._show_pre_signed_txs,
                '11': self._show_tx_history,
                '12': self._ping_network,
                '13': self._switch_network,
                '0': self._exit,
            }

            action = actions.get(choice)
            if action:
                try:
                    action()
                except PermissionError:
                    print(c("  Operation not available.", Colors.RED))
                except Exception as e:
                    print(c(f"  Error: {e}", Colors.RED))
            else:
                print(c("  Invalid option.", Colors.RED))

    def _show_wallet_info(self) -> None:
        info = self.app.get_wallet_info()
        print(c("\n  === Wallet Information ===\n", Colors.BOLD))
        for key, value in info.items():
            if isinstance(value, list):
                print(f"  {key}:")
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            print(f"    {k}: {v}")
                        print()
                    else:
                        print(f"    - {item}")
            else:
                print(f"  {key}: {c(str(value), Colors.CYAN)}")

    def _generate_address(self) -> None:
        addr = self.app.get_new_address()
        print(c(f"\n  New Address: {addr}", Colors.GREEN))

    def _create_child_wallet(self) -> None:
        print(c("\n  === Create Child Wallet ===\n", Colors.BOLD))
        name = input(c("  Wallet name: ", Colors.CYAN)).strip()
        if not name:
            print(c("  Name required.", Colors.RED))
            return

        nominee_name = input(
            c("  Nominee name (optional): ", Colors.CYAN)
        ).strip() or None
        nominee_address = input(
            c("  Nominee BTC address (optional): ", Colors.CYAN)
        ).strip() or None

        child = self.app.create_child_wallet(name, nominee_address, nominee_name)
        print(c(f"\n  Child wallet '{name}' created!", Colors.GREEN))
        print(f"  Address: {c(child.address, Colors.CYAN)}")
        print(f"  Path:    {c(child.derivation_path, Colors.DIM)}")
        if nominee_name:
            print(f"  Nominee: {c(nominee_name, Colors.YELLOW)}")

    def _list_child_wallets(self) -> None:
        children = self.app.list_child_wallets()
        if not children:
            print(c("\n  No child wallets found.", Colors.DIM))
            return

        print(c("\n  === Child Wallets ===\n", Colors.BOLD))
        for i, cw in enumerate(children, 1):
            print(f"  {i}. {c(cw['name'], Colors.BOLD)}")
            print(f"     Address:   {c(cw['address'], Colors.CYAN)}")
            print(f"     Allocated: {c(f\"{cw['allocated_btc']:.8f} BTC\", Colors.GREEN)}")
            print(f"     Path:      {c(cw['derivation_path'], Colors.DIM)}")
            if cw.get('nominee'):
                print(f"     Nominee:   {c(cw['nominee'], Colors.YELLOW)}")
                print(f"     Nom. Addr: {c(cw['nominee_address'], Colors.YELLOW)}")
            print()

    def _distribute_btc(self) -> None:
        print(c("\n  === Distribute BTC to Child Wallet ===\n", Colors.BOLD))
        child_name = input(c("  Child wallet name: ", Colors.CYAN)).strip()
        amount = input(c("  Amount (BTC): ", Colors.CYAN)).strip()
        fee = input(c("  Fee (BTC, default 0.0001): ", Colors.CYAN)).strip()

        try:
            amount_btc = float(amount)
            fee_btc = float(fee) if fee else 0.0001

            result = self.app.distribute_btc(child_name, amount_btc, fee_btc)

            print(c(f"\n  Distribution Transaction Created!", Colors.GREEN))
            print(f"  TXID:    {c(result['txid'], Colors.CYAN)}")
            print(f"  Amount:  {c(f\"{result['amount_btc']:.8f} BTC\", Colors.GREEN)}")
            print(f"  Fee:     {c(f\"{result['fee_btc']:.8f} BTC\", Colors.DIM)}")
            print(f"  To:      {c(result['child_address'], Colors.CYAN)}")
            print(f"\n  Raw TX:  {c(result['hex'][:80] + '...', Colors.DIM)}")
        except ValueError as e:
            print(c(f"  Error: {e}", Colors.RED))

    def _designate_nominee(self) -> None:
        print(c("\n  === Designate Nominee ===\n", Colors.BOLD))
        child_name = input(c("  Child wallet name: ", Colors.CYAN)).strip()
        nominee_name = input(c("  Nominee name: ", Colors.CYAN)).strip()
        nominee_address = input(c("  Nominee BTC address: ", Colors.CYAN)).strip()
        amount = input(c("  Amount to inherit (BTC): ", Colors.CYAN)).strip()

        try:
            amount_btc = float(amount)
            result = self.app.designate_nominee(
                child_name, nominee_name, nominee_address, amount_btc
            )
            print(c(f"\n  Nominee '{nominee_name}' designated!", Colors.GREEN))
            print(f"  Status: {c(result['status'], Colors.YELLOW)}")
        except ValueError as e:
            print(c(f"  Error: {e}", Colors.RED))

    def _pre_sign_inheritance(self) -> None:
        print(c("\n  === Pre-Sign Inheritance Transaction ===\n", Colors.BOLD))
        child_name = input(c("  Child wallet name: ", Colors.CYAN)).strip()
        fee = input(c("  Fee (BTC, default 0.0001): ", Colors.CYAN)).strip()
        locktime_str = input(
            c("  Locktime (block height, 0 for none): ", Colors.CYAN)
        ).strip()

        try:
            fee_btc = float(fee) if fee else 0.0001
            locktime = int(locktime_str) if locktime_str else 0

            result = self.app.pre_sign_inheritance(
                child_name, fee_btc, locktime
            )

            print(c(f"\n  Inheritance Transaction Pre-Signed!", Colors.GREEN))
            print(f"  TXID:     {c(result['txid'], Colors.CYAN)}")
            print(f"  Nominee:  {c(result['nominee'], Colors.YELLOW)}")
            print(f"  To:       {c(result['nominee_address'], Colors.CYAN)}")
            print(f"  Amount:   {c(f\"{result['amount_btc']:.8f} BTC\", Colors.GREEN)}")
            print(f"  Fee:      {c(f\"{result['fee_btc']:.8f} BTC\", Colors.DIM)}")
            print(f"  Status:   {c(result['status'], Colors.YELLOW)}")
            print(f"  Master Duplicate: {c('Stored', Colors.GREEN) if result['master_duplicate_stored'] else c('Not stored', Colors.RED)}")
            print(f"\n  Raw TX (for future broadcast):")
            print(f"  {c(result['raw_hex'][:120] + '...', Colors.DIM)}")
        except ValueError as e:
            print(c(f"  Error: {e}", Colors.RED))

    def _show_inheritance_summary(self) -> None:
        summary = self.app.get_inheritance_summary()
        print(c("\n  === Inheritance Summary ===\n", Colors.BOLD))
        print(f"  Total Nominees: {c(str(summary.get('total_nominees', 0)), Colors.CYAN)}")
        print(f"  Pre-Signed TXs: {c(str(summary.get('total_pre_signed', 0)), Colors.CYAN)}")
        print(f"  Total Allocated: {c(f\"{summary.get('total_allocated_btc', 0):.8f} BTC\", Colors.GREEN)}")

        nominees = summary.get('nominees', [])
        if nominees:
            print(c("\n  Nominees:", Colors.BOLD))
            for n in nominees:
                print(f"    - {c(n['nominee_name'], Colors.YELLOW)}: "
                      f"{c(f\"{n['amount_btc']:.8f} BTC\", Colors.GREEN)} "
                      f"via {c(n['child_wallet'], Colors.CYAN)} "
                      f"[{c(n['status'], Colors.DIM)}]")

        txs = summary.get('pre_signed_transactions', [])
        if txs:
            print(c("\n  Pre-Signed Transactions:", Colors.BOLD))
            for t in txs:
                dup_status = c("DUP", Colors.GREEN) if t['has_master_duplicate'] else c("NO DUP", Colors.RED)
                print(f"    - {c(t['txid'][:16] + '...', Colors.DIM)} -> "
                      f"{c(t['nominee'], Colors.YELLOW)} "
                      f"({c(f\"{t['amount_btc']:.8f} BTC\", Colors.GREEN)}) "
                      f"[{dup_status}]")

    def _add_utxo(self) -> None:
        print(c("\n  === Add UTXO (Testing) ===\n", Colors.BOLD))
        print(c("  This manually adds an unspent output for testing.\n", Colors.DIM))

        txid = input(c("  TXID (or 'demo' for demo): ", Colors.CYAN)).strip()
        if txid.lower() == 'demo':
            # Add a demo UTXO
            import secrets
            txid = secrets.token_hex(32)
            self.app.add_utxo(txid, 0, 1.0)
            print(c(f"  Demo UTXO added: 1.0 BTC", Colors.GREEN))
            print(f"  TXID: {c(txid, Colors.DIM)}")
            return

        vout = int(input(c("  Output index: ", Colors.CYAN)).strip())
        value = float(input(c("  Value (BTC): ", Colors.CYAN)).strip())

        self.app.add_utxo(txid, vout, value)
        print(c(f"  UTXO added: {value} BTC", Colors.GREEN))

    def _show_pre_signed_txs(self) -> None:
        if self.app.is_decoy_mode:
            print(c("\n  No pre-signed transactions.", Colors.DIM))
            return

        txs = self.app.master_wallet.get_pre_signed_txs()
        if not txs:
            print(c("\n  No pre-signed transactions.", Colors.DIM))
            return

        print(c("\n  === Pre-Signed Transactions (Master Duplicates) ===\n",
               Colors.BOLD))
        for i, tx in enumerate(txs, 1):
            print(f"  {i}. TXID: {c(tx['txid'][:32] + '...', Colors.CYAN)}")
            print(f"     From: {c(tx['source_wallet'], Colors.DIM)} "
                  f"({c(tx['source_address'], Colors.DIM)})")
            print(f"     To:   {c(tx['nominee_name'], Colors.YELLOW)} "
                  f"({c(tx['nominee_address'][:32] + '...', Colors.CYAN)})")
            print(f"     Amount: {c(f\"{satoshis_to_btc(tx['amount_satoshis']):.8f} BTC\", Colors.GREEN)}")
            print(f"     Master Duplicate: {c('Yes', Colors.GREEN) if tx.get('master_duplicate_hex') else c('No', Colors.RED)}")
            print()

    def _show_tx_history(self) -> None:
        history = self.app.get_transaction_history()
        if not history:
            print(c("\n  No transaction history.", Colors.DIM))
            return

        print(c("\n  === Transaction History ===\n", Colors.BOLD))
        for tx in history:
            direction = tx.get('direction', 'unknown')
            arrow = c("-->", Colors.RED) if direction == "sent" else c("<--", Colors.GREEN)
            amount = satoshis_to_btc(tx.get('amount', 0))
            ts = time.strftime('%Y-%m-%d %H:%M',
                               time.localtime(tx.get('timestamp', 0)))
            confs = tx.get('confirmations', 0)
            print(f"  {arrow} {c(f'{amount:.8f} BTC', Colors.BOLD)} "
                  f"  {c(ts, Colors.DIM)}  "
                  f"({c(str(confs), Colors.CYAN)} confirmations)")
            print(f"      {c(tx.get('txid', '')[:48] + '...', Colors.DIM)}")

    def _ping_network(self) -> None:
        """Ping current network endpoints and show results."""
        print(c("\n  === Ping Network ===\n", Colors.BOLD))
        result = self.app.ping_network()
        net_label = result['network'].upper()
        net_color = Colors.GREEN if result['network'] == 'testnet' else Colors.RED
        print(f"  Network: {c(net_label, net_color)}")
        print(f"  Connected: {c('Yes', Colors.GREEN) if result['connected'] else c('No', Colors.RED)}")
        if result['block_height']:
            print(f"  Block Height: {c(str(result['block_height']), Colors.CYAN)}")
        print()
        for ep in result['endpoints']:
            if ep['reachable']:
                print(f"    {c('OK', Colors.GREEN)}  {ep['url']}")
                print(f"         Latency: {c(f\"{ep['latency_ms']}ms\", Colors.CYAN)}  "
                      f"Block: {c(str(ep['block_height']), Colors.CYAN)}")
            else:
                print(f"    {c('FAIL', Colors.RED)}  {ep['url']}")

    def _switch_network(self) -> None:
        """Switch between testnet and mainnet."""
        current = 'testnet' if self.app.testnet else 'mainnet'
        target = 'mainnet' if self.app.testnet else 'testnet'
        print(c(f"\n  Current network: {current.upper()}", Colors.BOLD))
        print(f"  Switch to {c(target.upper(), Colors.YELLOW)}?")

        if target == 'mainnet':
            print(c("\n  WARNING: Mainnet uses real Bitcoin!", Colors.RED))
            print(c("  Only switch if you know what you are doing.", Colors.RED))

        confirm = input(c(f"\n  Type 'yes' to switch to {target}: ", Colors.CYAN)).strip().lower()
        if confirm == 'yes':
            self.app.switch_network(testnet=(target == 'testnet'))
            print(c(f"\n  Switched to {target.upper()}", Colors.GREEN))
        else:
            print(c("  Cancelled.", Colors.DIM))

    def _exit(self) -> None:
        print(c("\n  Goodbye! Your wallet data is safely encrypted.\n",
               Colors.GREEN))
        self.running = False


def main():
    """Entry point for the BITWILL CLI."""
    import argparse
    parser = argparse.ArgumentParser(
        description="BITWILL - Blockchain Inheritance & Security"
    )
    parser.add_argument('--storage-dir', default=None,
                        help='Storage directory (default: ~/.bitwill)')
    parser.add_argument('--mainnet', action='store_true',
                        help='Use Bitcoin mainnet (default: testnet)')
    args = parser.parse_args()

    cli = BitWillCLI(
        storage_dir=args.storage_dir,
        testnet=not args.mainnet
    )
    cli.start()


if __name__ == '__main__':
    main()
