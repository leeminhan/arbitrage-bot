import json
import threading
from websocket import WebSocketApp
import websocket
import time
import warnings
from web3 import Web3
import ssl

warnings.filterwarnings('ignore', message='.*OpenSSL.*')

# Binance WebSocket endpoint for BNB/USDT
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/bnbusdt@ticker"

# BSC RPC endpoint
BSC_RPC = "https://bsc-dataseed.binance.org/"

# Global variable to store latest prices
latest_binance_price = None
latest_pancake_price = None
price_lock = threading.Lock()

class PriceMonitor:
    def __init__(self):
        self.w3 = self.connect_to_bsc()
        if self.w3 is None:
            raise Exception("Could not establish connection to BSC")
        
        self.setup_contracts()
        self.ws = None
        self.running = True
        self.last_message_time = time.time()
        
    def on_message(self, ws, message):
        global latest_binance_price
        self.last_message_time = time.time()
        try:
            data = json.loads(message)
            if 'c' in data:  # Close price
                with price_lock:
                    latest_binance_price = float(data['c'])
                    print(f"[Binance WS] New price: {latest_binance_price}")
                self.check_arbitrage()
        except Exception as e:
            print(f"[Binance WS] Message processing error: {e}")

    def on_error(self, ws, error):
        print(f"[Binance WS] Error occurred: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[Binance WS] Connection closed: {close_status_code} - {close_msg}")
        if self.running:
            print("[Binance WS] Reconnecting in 5 seconds...")
            time.sleep(5)
            self.start_websocket()

    def on_pong(self, ws, message):
        self.last_message_time = time.time()
        print("[Binance WS] Pong received")

    def on_ping(self, ws, message):
        self.last_message_time = time.time()
        print("[Binance WS] Ping received")

    def on_open(self, ws):
        print("[Binance WS] Connection established")
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": [
                "bnbusdt@ticker"
            ],
            "id": 1
        }
        ws.send(json.dumps(subscribe_message))

    def connection_monitor(self):
        while self.running:
            if time.time() - self.last_message_time > 30:  # No messages for 30 seconds
                print("[Binance WS] Connection seems dead, restarting...")
                self.ws.close()
                self.start_websocket()
            time.sleep(5)

    def start_websocket(self):
        websocket.enableTrace(False)  # Disable verbose logging
        self.ws = WebSocketApp(
            BINANCE_WS_URL,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
            on_ping=self.on_ping,
            on_pong=self.on_pong
        )
        
        # Start connection monitor in separate thread
        monitor_thread = threading.Thread(target=self.connection_monitor)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Start WebSocket with custom settings
        self.ws.run_forever(
            ping_interval=20,
            ping_timeout=10,
            ping_payload='',
            sslopt={"cert_reqs": ssl.CERT_NONE}
        )

    def connect_to_bsc(self):
        try:
            w3 = Web3(Web3.HTTPProvider(BSC_RPC))
            if w3.is_connected():
                print("Successfully connected to BSC")
                return w3
            print("Failed to connect to BSC")
            return None
        except Exception as e:
            print(f"Error connecting to BSC: {str(e)}")
            return None

    def setup_contracts(self):
        self.WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
        self.USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
        self.PANCAKE_PAIR_ADDRESS = "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE"
        
        self.UNISWAP_PAIR_ABI = [
            {
                "constant": True,
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
                    {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
                    {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
                ],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token0",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }
        ]
        
        self.pair_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.PANCAKE_PAIR_ADDRESS),
            abi=self.UNISWAP_PAIR_ABI
        )

    def get_pancake_price(self):
        try:
            if not self.w3.is_connected():
                print("[Pancake Error] Not connected to BSC")
                return None

            reserves = self.pair_contract.functions.getReserves().call()
            token0 = self.pair_contract.functions.token0().call()
            
            bnb_first = token0.lower() == self.WBNB_ADDRESS.lower()
            
            reserve_bnb = reserves[0] if bnb_first else reserves[1]
            reserve_usdt = reserves[1] if bnb_first else reserves[0]
            
            price = (reserve_usdt / (10 ** 18)) / (reserve_bnb / (10 ** 18))
            print(f"[PancakeSwap] Got new price: {price}")
            return price
        except Exception as e:
            print(f"[Pancake Error] {str(e)}")
            return None

    def check_arbitrage(self, threshold_pct=0.2):
        global latest_binance_price
        
        with price_lock:
            binance_price = latest_binance_price
        
        pancake_price = self.get_pancake_price()

        if binance_price is None or pancake_price is None:
            return

        diff = binance_price - pancake_price
        diff_pct = (diff / pancake_price) * 100

        print(f"[BNB] Binance: {binance_price:.3f} | PancakeSwap: {pancake_price:.3f} | Diff: {diff_pct:.2f}%")

        if abs(diff_pct) >= threshold_pct:
            if diff > 0:
                print(f"⚡ Arbitrage Opportunity: Buy on PancakeSwap, Sell on Binance (+{diff_pct:.2f}%)")
            else:
                print(f"⚡ Arbitrage Opportunity: Buy on Binance, Sell on PancakeSwap (+{-diff_pct:.2f}%)")

def main():
    while True:
        try:
            monitor = PriceMonitor()
            
            # Start WebSocket in a separate thread
            ws_thread = threading.Thread(target=monitor.start_websocket)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Main loop
            while True:
                time.sleep(1)
                if not ws_thread.is_alive():
                    print("[Main] WebSocket thread died, restarting...")
                    break
                
        except Exception as e:
            print(f"[Main] Error occurred: {e}")
            time.sleep(5)  # Wait before retrying

if __name__ == "__main__":
    main()