"""
Blockchain network integration for BITWILL.
Provides balance lookups, transaction broadcasting, fee estimation,
and UTXO fetching via public blockchain APIs.

Supports both testnet and mainnet via multiple API backends
with automatic fallback.
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from ..core.transaction import satoshis_to_btc, btc_to_satoshis


# API endpoints
BLOCKSTREAM_MAINNET = "https://blockstream.info/api"
BLOCKSTREAM_TESTNET = "https://blockstream.info/testnet/api"
MEMPOOL_MAINNET = "https://mempool.space/api"
MEMPOOL_TESTNET = "https://mempool.space/testnet/api"


@dataclass
class NetworkUTXO:
    """A UTXO fetched from the network."""
    txid: str
    vout: int
    value: int  # satoshis
    status_confirmed: bool
    block_height: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AddressInfo:
    """Address information from the network."""
    address: str
    balance_sat: int
    total_received_sat: int
    total_sent_sat: int
    tx_count: int
    unconfirmed_balance_sat: int = 0

    @property
    def balance_btc(self) -> float:
        return satoshis_to_btc(self.balance_sat)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['balance_btc'] = self.balance_btc
        return d


@dataclass
class FeeEstimate:
    """Fee rate estimates in sat/vB."""
    fastest: int    # next block
    half_hour: int  # ~3 blocks
    hour: int       # ~6 blocks
    economy: int    # ~12+ blocks
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class BlockchainAPI:
    """
    Blockchain API client with multiple backend support.
    Uses Blockstream (primary) and mempool.space (fallback).
    """

    def __init__(self, testnet: bool = True, timeout: int = 15):
        self.testnet = testnet
        self.timeout = timeout

        if testnet:
            self._primary = BLOCKSTREAM_TESTNET
            self._fallback = MEMPOOL_TESTNET
        else:
            self._primary = BLOCKSTREAM_MAINNET
            self._fallback = MEMPOOL_MAINNET

        self._fee_cache: Optional[FeeEstimate] = None
        self._fee_cache_time: float = 0
        self._FEE_CACHE_TTL = 60  # cache fees for 60 seconds

    def _request(self, url: str, method: str = "GET",
                 data: Optional[bytes] = None,
                 content_type: Optional[str] = None) -> bytes:
        """Make an HTTP request with timeout."""
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("User-Agent", "BITWILL/1.0")
        if content_type:
            req.add_header("Content-Type", content_type)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def _get_json(self, path: str) -> dict:
        """GET JSON from primary API, fall back to secondary."""
        for base in (self._primary, self._fallback):
            try:
                raw = self._request(f"{base}{path}")
                return json.loads(raw)
            except (urllib.error.URLError, json.JSONDecodeError, OSError):
                continue
        raise ConnectionError(f"All API backends failed for {path}")

    def _get_text(self, path: str) -> str:
        """GET text from primary API, fall back to secondary."""
        for base in (self._primary, self._fallback):
            try:
                raw = self._request(f"{base}{path}")
                return raw.decode("utf-8")
            except (urllib.error.URLError, OSError):
                continue
        raise ConnectionError(f"All API backends failed for {path}")

    def _post_text(self, path: str, body: str) -> str:
        """POST text data to primary API, fall back to secondary."""
        for base in (self._primary, self._fallback):
            try:
                raw = self._request(
                    f"{base}{path}",
                    method="POST",
                    data=body.encode("utf-8"),
                    content_type="text/plain"
                )
                return raw.decode("utf-8")
            except (urllib.error.URLError, OSError):
                continue
        raise ConnectionError(f"All API backends failed for POST {path}")

    # --- Public API ---

    def get_address_info(self, address: str) -> AddressInfo:
        """Fetch address balance and transaction count."""
        data = self._get_json(f"/address/{address}")
        stats = data.get("chain_stats", {})
        mempool = data.get("mempool_stats", {})

        confirmed_balance = (
            stats.get("funded_txo_sum", 0) -
            stats.get("spent_txo_sum", 0)
        )
        unconfirmed_balance = (
            mempool.get("funded_txo_sum", 0) -
            mempool.get("spent_txo_sum", 0)
        )

        return AddressInfo(
            address=address,
            balance_sat=confirmed_balance,
            total_received_sat=stats.get("funded_txo_sum", 0),
            total_sent_sat=stats.get("spent_txo_sum", 0),
            tx_count=stats.get("tx_count", 0) + mempool.get("tx_count", 0),
            unconfirmed_balance_sat=unconfirmed_balance,
        )

    def get_utxos(self, address: str) -> List[NetworkUTXO]:
        """Fetch unspent transaction outputs for an address."""
        data = self._get_json(f"/address/{address}/utxo")
        utxos = []
        for item in data:
            status = item.get("status", {})
            utxos.append(NetworkUTXO(
                txid=item["txid"],
                vout=item["vout"],
                value=item["value"],
                status_confirmed=status.get("confirmed", False),
                block_height=status.get("block_height"),
            ))
        return utxos

    def get_transaction(self, txid: str) -> Dict:
        """Fetch transaction details."""
        return self._get_json(f"/tx/{txid}")

    def get_transaction_hex(self, txid: str) -> str:
        """Fetch raw transaction hex."""
        return self._get_text(f"/tx/{txid}/hex")

    def get_transaction_status(self, txid: str) -> Dict:
        """Fetch transaction confirmation status."""
        return self._get_json(f"/tx/{txid}/status")

    def broadcast_transaction(self, raw_hex: str) -> str:
        """
        Broadcast a signed transaction to the network.
        Returns the txid on success.
        Raises ConnectionError or ValueError on failure.
        """
        txid = self._post_text("/tx", raw_hex)
        # Blockstream API returns the txid as plain text on success
        txid = txid.strip()
        if len(txid) == 64:
            return txid
        raise ValueError(f"Broadcast failed: {txid}")

    def get_fee_estimates(self) -> FeeEstimate:
        """
        Get current fee rate estimates in sat/vB.
        Results are cached for 60 seconds.
        """
        now = time.time()
        if (self._fee_cache and
                now - self._fee_cache_time < self._FEE_CACHE_TTL):
            return self._fee_cache

        data = self._get_json("/fee-estimates")
        # Blockstream returns {"1": rate, "3": rate, "6": rate, ...}
        # Keys are target confirmation blocks
        estimate = FeeEstimate(
            fastest=int(data.get("1", data.get("2", 20))),
            half_hour=int(data.get("3", 10)),
            hour=int(data.get("6", 5)),
            economy=int(data.get("25", data.get("144", 1))),
            timestamp=now,
        )
        self._fee_cache = estimate
        self._fee_cache_time = now
        return estimate

    def get_block_height(self) -> int:
        """Get the current block height."""
        text = self._get_text("/blocks/tip/height")
        return int(text.strip())

    def get_address_transactions(self, address: str,
                                  limit: int = 25) -> List[Dict]:
        """Fetch recent transactions for an address."""
        data = self._get_json(f"/address/{address}/txs")
        return data[:limit]

    def estimate_tx_fee(self, num_inputs: int, num_outputs: int,
                        target_blocks: int = 6) -> int:
        """
        Estimate the fee for a transaction in satoshis.
        Uses approximate P2PKH transaction size.
        """
        fees = self.get_fee_estimates()

        if target_blocks <= 1:
            rate = fees.fastest
        elif target_blocks <= 3:
            rate = fees.half_hour
        elif target_blocks <= 6:
            rate = fees.hour
        else:
            rate = fees.economy

        # Approximate P2PKH transaction size
        # 10 bytes overhead + 148 bytes per input + 34 bytes per output
        estimated_size = 10 + (num_inputs * 148) + (num_outputs * 34)
        return rate * estimated_size

    def ping(self) -> Dict:
        """
        Ping blockchain API endpoints and return detailed connectivity info.
        Returns latency, block height, and endpoint status for each backend.
        """
        results = {
            'network': 'testnet' if self.testnet else 'mainnet',
            'endpoints': [],
            'connected': False,
            'block_height': None,
        }

        for label, base_url in [("primary", self._primary),
                                 ("fallback", self._fallback)]:
            endpoint_result = {
                'label': label,
                'url': base_url,
                'reachable': False,
                'latency_ms': None,
                'block_height': None,
            }
            try:
                start = time.time()
                raw = self._request(f"{base_url}/blocks/tip/height")
                latency = (time.time() - start) * 1000
                height = int(raw.decode("utf-8").strip())
                endpoint_result['reachable'] = True
                endpoint_result['latency_ms'] = round(latency, 1)
                endpoint_result['block_height'] = height
                results['connected'] = True
                if results['block_height'] is None:
                    results['block_height'] = height
            except (urllib.error.URLError, OSError, ValueError):
                pass
            results['endpoints'].append(endpoint_result)

        return results

    def check_connectivity(self) -> bool:
        """Check if we can reach the blockchain API."""
        try:
            self.get_block_height()
            return True
        except (ConnectionError, OSError):
            return False
