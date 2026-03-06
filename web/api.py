"""
BITWILL REST API.
Flask-based API for wallet operations, inheritance management,
and blockchain network integration.
"""

import io
import os
import base64
import secrets
import time
from functools import wraps
from typing import Optional

from flask import Flask, request, jsonify, render_template, session, send_file

from ..wallet.bitwill_app import BitWillApp
from ..core.transaction import satoshis_to_btc


def create_app(storage_dir: Optional[str] = None,
               testnet: bool = True) -> Flask:
    """Create and configure the Flask application."""

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.secret_key = secrets.token_hex(32)

    # Store app instances per session (keyed by session token)
    _instances: dict = {}

    def _get_app_instance() -> Optional[BitWillApp]:
        token = session.get("wallet_token")
        if token and token in _instances:
            return _instances[token]
        return None

    def require_wallet(f):
        """Decorator: endpoint requires an unlocked wallet."""
        @wraps(f)
        def wrapper(*args, **kwargs):
            bw = _get_app_instance()
            if not bw or not bw.is_initialized:
                return jsonify({"error": "Wallet not unlocked"}), 401
            return f(bw, *args, **kwargs)
        return wrapper

    # --- Pages ---

    @app.route("/")
    def index():
        return render_template("index.html")

    # --- Auth / Wallet lifecycle ---

    @app.route("/api/status", methods=["GET"])
    def wallet_status():
        sdir = storage_dir or os.path.expanduser("~/.bitwill")
        tmp = BitWillApp(storage_dir=sdir, testnet=testnet)
        bw = _get_app_instance()
        current_network = "testnet" if testnet else "mainnet"
        if bw and bw.is_initialized:
            current_network = "testnet" if bw.testnet else "mainnet"
        return jsonify({
            "wallet_exists": tmp.wallet_exists(),
            "unlocked": bw is not None and bw.is_initialized,
            "network": current_network,
            "mainnet_available": True,
        })

    @app.route("/api/create", methods=["POST"])
    def create_wallet():
        data = request.get_json(force=True)
        password = data.get("password", "")
        passphrase = data.get("passphrase", "")
        strength = data.get("strength", 256)

        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        sdir = storage_dir or os.path.expanduser("~/.bitwill")
        bw = BitWillApp(storage_dir=sdir, testnet=testnet)
        mnemonic = bw.create_wallet(password, passphrase, strength)

        token = secrets.token_hex(32)
        _instances[token] = bw
        session["wallet_token"] = token

        return jsonify({"mnemonic": mnemonic, "address": bw.get_address()})

    @app.route("/api/restore", methods=["POST"])
    def restore_wallet():
        data = request.get_json(force=True)
        mnemonic = data.get("mnemonic", "")
        password = data.get("password", "")
        passphrase = data.get("passphrase", "")

        sdir = storage_dir or os.path.expanduser("~/.bitwill")
        bw = BitWillApp(storage_dir=sdir, testnet=testnet)
        try:
            bw.restore_wallet(mnemonic, password, passphrase)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        token = secrets.token_hex(32)
        _instances[token] = bw
        session["wallet_token"] = token

        return jsonify({"address": bw.get_address()})

    @app.route("/api/unlock", methods=["POST"])
    def unlock_wallet():
        data = request.get_json(force=True)
        password = data.get("password", "")
        passphrase = data.get("passphrase", "")

        sdir = storage_dir or os.path.expanduser("~/.bitwill")
        bw = BitWillApp(storage_dir=sdir, testnet=testnet)

        try:
            is_real = bw.unlock(password, passphrase)
        except FileNotFoundError:
            return jsonify({"error": "No wallet found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        token = secrets.token_hex(32)
        _instances[token] = bw
        session["wallet_token"] = token

        return jsonify({
            "unlocked": True,
            "address": bw.get_address(),
            "balance_btc": bw.get_balance(),
            "panic_events": len(bw.get_panic_log()) if is_real else 0,
        })

    @app.route("/api/lock", methods=["POST"])
    def lock_wallet():
        token = session.pop("wallet_token", None)
        if token and token in _instances:
            del _instances[token]
        return jsonify({"locked": True})

    # --- Wallet info ---

    @app.route("/api/wallet", methods=["GET"])
    @require_wallet
    def get_wallet_info(bw: BitWillApp):
        return jsonify(bw.get_wallet_info())

    @app.route("/api/balance", methods=["GET"])
    @require_wallet
    def get_balance(bw: BitWillApp):
        return jsonify({
            "balance_btc": bw.get_balance(),
            "address": bw.get_address(),
        })

    @app.route("/api/address/new", methods=["POST"])
    @require_wallet
    def new_address(bw: BitWillApp):
        addr = bw.get_new_address()
        return jsonify({"address": addr})

    # --- Child wallets ---

    @app.route("/api/children", methods=["GET"])
    @require_wallet
    def list_children(bw: BitWillApp):
        return jsonify(bw.list_child_wallets())

    @app.route("/api/children", methods=["POST"])
    @require_wallet
    def create_child(bw: BitWillApp):
        data = request.get_json(force=True)
        name = data.get("name", "")
        if not name:
            return jsonify({"error": "Name required"}), 400
        try:
            child = bw.create_child_wallet(
                name,
                nominee_address=data.get("nominee_address"),
                nominee_name=data.get("nominee_name"),
            )
            return jsonify({
                "name": child.name,
                "address": child.address,
                "derivation_path": child.derivation_path,
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/distribute", methods=["POST"])
    @require_wallet
    def distribute_btc(bw: BitWillApp):
        data = request.get_json(force=True)
        try:
            result = bw.distribute_btc(
                data["child_name"],
                float(data["amount_btc"]),
                float(data.get("fee_btc", 0.0001)),
            )
            return jsonify(result)
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400

    # --- Inheritance ---

    @app.route("/api/nominee", methods=["POST"])
    @require_wallet
    def designate_nominee(bw: BitWillApp):
        data = request.get_json(force=True)
        try:
            result = bw.designate_nominee(
                data["child_wallet_name"],
                data["nominee_name"],
                data["nominee_address"],
                float(data["amount_btc"]),
            )
            return jsonify(result)
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/presign", methods=["POST"])
    @require_wallet
    def pre_sign(bw: BitWillApp):
        data = request.get_json(force=True)
        try:
            result = bw.pre_sign_inheritance(
                data["child_wallet_name"],
                float(data.get("fee_btc", 0.0001)),
                int(data.get("locktime", 0)),
            )
            return jsonify(result)
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/inheritance", methods=["GET"])
    @require_wallet
    def inheritance_summary(bw: BitWillApp):
        return jsonify(bw.get_inheritance_summary())

    @app.route("/api/presigned-txs", methods=["GET"])
    @require_wallet
    def list_presigned(bw: BitWillApp):
        txs = bw.master_wallet.get_pre_signed_txs()
        return jsonify(txs)

    # --- Network integration ---

    @app.route("/api/network/status", methods=["GET"])
    @require_wallet
    def network_status(bw: BitWillApp):
        return jsonify(bw.check_network())

    @app.route("/api/network/ping", methods=["GET"])
    def ping_network():
        """Ping blockchain endpoints (works without wallet unlock)."""
        from ..network.blockchain import BlockchainAPI
        network = request.args.get("network", "testnet")
        is_testnet = network != "mainnet"
        api = BlockchainAPI(testnet=is_testnet)
        return jsonify(api.ping())

    @app.route("/api/network/ping-all", methods=["GET"])
    def ping_all_networks():
        """Ping both testnet and mainnet endpoints."""
        from ..network.blockchain import BlockchainAPI
        results = {}
        for label, is_testnet in [("testnet", True), ("mainnet", False)]:
            api = BlockchainAPI(testnet=is_testnet)
            results[label] = api.ping()
        return jsonify(results)

    @app.route("/api/network/switch", methods=["POST"])
    @require_wallet
    def switch_network(bw: BitWillApp):
        """Switch between testnet and mainnet."""
        data = request.get_json(force=True)
        network = data.get("network", "")
        if network not in ("testnet", "mainnet"):
            return jsonify({"error": "network must be 'testnet' or 'mainnet'"}), 400
        is_testnet = network == "testnet"
        bw.switch_network(testnet=is_testnet)
        return jsonify({
            "network": network,
            "switched": True,
        })

    @app.route("/api/network/balance", methods=["GET"])
    @require_wallet
    def network_balance(bw: BitWillApp):
        address = request.args.get("address") or bw.get_address()
        try:
            return jsonify(bw.sync_balance(address))
        except ConnectionError as e:
            return jsonify({"error": str(e)}), 503

    @app.route("/api/network/utxos", methods=["POST"])
    @require_wallet
    def sync_utxos(bw: BitWillApp):
        try:
            utxos = bw.sync_utxos()
            return jsonify({"utxos": utxos, "count": len(utxos)})
        except ConnectionError as e:
            return jsonify({"error": str(e)}), 503

    @app.route("/api/network/fees", methods=["GET"])
    @require_wallet
    def fee_estimates(bw: BitWillApp):
        try:
            return jsonify(bw.get_fee_estimates())
        except ConnectionError as e:
            return jsonify({"error": str(e)}), 503

    @app.route("/api/network/broadcast", methods=["POST"])
    @require_wallet
    def broadcast_tx(bw: BitWillApp):
        data = request.get_json(force=True)
        raw_hex = data.get("raw_hex", "")
        if not raw_hex:
            return jsonify({"error": "raw_hex required"}), 400
        try:
            txid = bw.broadcast_transaction(raw_hex)
            return jsonify({"txid": txid})
        except (ConnectionError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/network/broadcast-inheritance", methods=["POST"])
    @require_wallet
    def broadcast_inheritance(bw: BitWillApp):
        data = request.get_json(force=True)
        child_name = data.get("child_wallet_name", "")
        try:
            result = bw.broadcast_pre_signed(child_name)
            return jsonify(result)
        except (ValueError, ConnectionError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/network/tx-status/<txid>", methods=["GET"])
    @require_wallet
    def tx_status(bw: BitWillApp, txid: str):
        try:
            return jsonify(bw.get_tx_status(txid))
        except ConnectionError as e:
            return jsonify({"error": str(e)}), 503

    @app.route("/api/network/history", methods=["GET"])
    @require_wallet
    def network_history(bw: BitWillApp):
        address = request.args.get("address") or bw.get_address()
        try:
            return jsonify(bw.get_network_tx_history(address))
        except ConnectionError as e:
            return jsonify({"error": str(e)}), 503

    # --- QR Code ---

    @app.route("/api/qrcode", methods=["GET"])
    @require_wallet
    def generate_qr(bw: BitWillApp):
        """Generate QR code for an address. Returns PNG image or base64 data."""
        address = request.args.get("address") or bw.get_address()
        data = request.args.get("data") or f"bitcoin:{address}"
        fmt = request.args.get("format", "base64")  # "base64" or "png"

        try:
            import qrcode
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            if fmt == "png":
                return send_file(buf, mimetype="image/png",
                                 download_name="qrcode.png")
            else:
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return jsonify({
                    "qr_base64": b64,
                    "address": address,
                    "data": data,
                })
        except ImportError:
            return jsonify({"error": "qrcode package not installed"}), 500

    # --- Testing helpers ---

    @app.route("/api/add-utxo", methods=["POST"])
    @require_wallet
    def add_utxo(bw: BitWillApp):
        data = request.get_json(force=True)
        try:
            bw.add_utxo(
                data["txid"], int(data["vout"]),
                float(data["value_btc"]),
                data.get("address"),
            )
            return jsonify({"ok": True})
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400

    return app
