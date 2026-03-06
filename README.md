# BITWILL - Blockchain Inheritance & Will Security System

A Bitcoin wallet application with built-in inheritance planning and panic mode security. BITWILL enables users to create HD wallets, designate nominees for child wallets, pre-sign inheritance transactions, and protect funds under duress with a decoy wallet system.

## Features

- **HD Wallet Management** - BIP-32/39/44 compliant hierarchical deterministic wallets
- **Child Wallets** - Create multiple named child wallets with individual Bitcoin addresses
- **Inheritance Planning** - Designate nominees and pre-sign inheritance transactions ready to broadcast
- **Panic Mode** - Decoy wallet shown on wrong password to protect funds under coercion
- **Encrypted Storage** - AES-256-GCM encryption with PBKDF2 key derivation (600k iterations)
- **Network Integration** - Live balance, UTXO sync, fee estimation, and transaction broadcasting via Blockstream/mempool.space APIs
- **Multiple Interfaces** - CLI, REST API, and Web UI

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/bitwilll/Claude.git
cd Claude
```

### 2. Create a Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate          # Windows
```

### 3. Install Dependencies

**Full installation (CLI + Web + all features):**
```bash
pip install -e ".[full]"
```

**Or install from requirements.txt:**
```bash
pip install -r requirements.txt
```

**Minimal installation (core wallet only):**
```bash
pip install -e .
```

## Running the Application

### Option 1: CLI Interface

```bash
# Using the entry point (after pip install -e)
bitwill

# Or run directly
python run.py

# Or as a Python module
python -m bitwill
```

You will be presented with a menu to:
1. **Create a new wallet** - Generates a BIP-39 mnemonic and creates an encrypted wallet
2. **Restore from mnemonic** - Recover an existing wallet using your seed phrase

After unlocking, the main menu provides:

| Option | Description |
|--------|-------------|
| 1 | View wallet info and addresses |
| 2 | Generate a new receiving address |
| 3 | Create a child wallet |
| 4 | List all child wallets |
| 5 | Distribute BTC to a child wallet |
| 6 | Designate a nominee for inheritance |
| 7 | Pre-sign an inheritance transaction |
| 8 | View inheritance summary |
| 9 | Add UTXO (for testing) |
| 10 | View pre-signed transactions |
| 11 | Transaction history |

### Option 2: Web Interface

```bash
# Using the entry point
bitwill-web

# Or run the server directly
python -m bitwill.web.server
```

The web server starts at **http://localhost:5000** by default.

### Option 3: REST API

The web server exposes a full REST API:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/create` | Create a new wallet |
| POST | `/api/restore` | Restore wallet from mnemonic |
| POST | `/api/unlock` | Unlock wallet with password |
| POST | `/api/lock` | Lock wallet |
| GET | `/api/status` | Check wallet status |
| GET | `/api/wallet` | Get wallet information |
| GET | `/api/balance` | Get BTC balance |
| POST | `/api/address/new` | Generate new address |
| GET | `/api/children` | List child wallets |
| POST | `/api/children` | Create child wallet |
| POST | `/api/distribute` | Distribute BTC to child |
| POST | `/api/nominee` | Designate nominee |
| POST | `/api/presign` | Pre-sign inheritance TX |
| GET | `/api/inheritance` | Inheritance summary |
| GET | `/api/network/status` | Blockchain connectivity |
| GET | `/api/network/fees` | Fee estimates |
| POST | `/api/network/broadcast` | Broadcast transaction |

## Running Tests

```bash
python -m pytest tests/
```

## How It Works

### Wallet Creation
When you create a wallet, BITWILL generates a 12-24 word BIP-39 mnemonic phrase. This seed phrase, combined with your password, derives the master HD key from which all child keys are generated. **Write down your mnemonic and store it securely - it is the only way to recover your wallet.**

### Inheritance Flow
1. Create child wallets for each beneficiary
2. Distribute BTC to child wallets
3. Designate nominees (inheritance recipients) for each child wallet
4. Pre-sign inheritance transactions - these are signed and stored, ready to broadcast at any time without needing wallet access

### Panic Mode
If someone forces you to open your wallet, entering the wrong password will not show an error. Instead, it displays a convincing decoy wallet with fake balances and transactions. The real wallet remains hidden and protected. All unauthorized access attempts are logged.

## Project Structure

```
bitwill/
├── core/               # Cryptographic primitives
│   ├── crypto_utils.py   # SHA-256, RIPEMD-160, secp256k1, Base58
│   ├── hd_key.py         # BIP-32 HD key derivation
│   ├── mnemonic.py       # BIP-39 mnemonic generation
│   └── transaction.py    # Bitcoin transaction construction & signing
├── wallet/             # Wallet logic
│   ├── master_wallet.py  # HD wallet management
│   └── bitwill_app.py    # Application controller
├── inheritance/        # Inheritance system
│   └── nominee.py        # Nominee records & pre-signed transactions
├── security/           # Security features
│   └── panic_mode.py     # Panic mode & decoy wallet
├── network/            # Blockchain integration
│   └── blockchain.py     # Blockstream/mempool.space API client
├── storage/            # Persistence
│   └── encrypted_store.py # AES-256-GCM encrypted storage
├── cli/                # Command-line interface
│   └── interface.py      # Rich terminal UI
├── web/                # Web interface
│   ├── api.py            # Flask REST API
│   ├── server.py         # WSGI entry point
│   ├── templates/        # HTML templates
│   └── static/           # CSS & assets
├── tests/              # Test suite
├── setup.py            # Package configuration
├── requirements.txt    # Dependencies
└── run.py              # Standalone runner
```

## Security Notes

- All wallet data is encrypted at rest using AES-256-GCM
- Passwords are processed through PBKDF2 with 600,000 iterations
- Private keys never leave the local machine
- Bitcoin cryptography (ECDSA, BIP-32, BIP-39) is implemented from scratch
- Supports both testnet and mainnet

## License

This project is for educational and personal use.
