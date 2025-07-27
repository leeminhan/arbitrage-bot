import json
import threading
from websocket import WebSocketApp
import websocket
import time
import warnings
from web3 import Web3
import ssl

# Update the BSC WebSocket endpoint to use public node
BSC_WS_URL = "wss://bsc.publicnode.com"
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/bnbusdt@ticker"

warnings.filterwarnings('ignore', message='.*OpenSSL.*')

# BSC RPC endpoint
BSC_RPC = "https://bsc-dataseed.binance.org/"

# Global variable to store latest prices
latest_binance_price = None
latest_pancake_price = None
price_lock = threading.Lock()

class PriceMonitor:
    def __init__(self):
        self.setup_contracts()
        self.binance_ws = None
        self.bsc_ws = None
        self.running = True
        self.last_binance_message_time = time.time()
        self.last_bsc_message_time = time.time()

    def setup_bsc_subscription(self):
        # Subscribe to the PancakeSwap pair contract events
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": [
                "logs",
                {
                    "address": self.PANCAKE_PAIR_ADDRESS,
                    "topics": [
                        "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"  # Sync event
                    ]
                }
            ]
        }

    def on_bsc_open(self, ws):
        print("[BSC WS] Connection established")
        # Start with a simpler subscription to test connection
        test_sub = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newHeads"]
        }
        ws.send(json.dumps(test_sub))
        print("[BSC WS] Initial subscription sent")

        # After confirming connection, subscribe to PancakeSwap events
        pair_sub = self.setup_bsc_subscription()
        ws.send(json.dumps(pair_sub))
        print("[BSC WS] PancakeSwap subscription sent")

    def on_bsc_message(self, ws, message):
        try:
            self.last_bsc_message_time = time.time()
            data = json.loads(message)
            
            # Handle subscription confirmation
            if 'id' in data:
                print(f"[BSC WS] Subscription response: {data}")
                return
            
            # Handle actual events
            if 'params' in data and 'result' in data['params']:
                result = data['params']['result']
                
                # Check if this is a newHeads message (contains baseFeePerGas)
                if 'baseFeePerGas' in result:
                    # print("[BSC WS] New block header received")
                    return
                
                # Check if this is a PancakeSwap Sync event
                if 'address' in result and result['address'].lower() == self.PANCAKE_PAIR_ADDRESS.lower():
                    print("[BSC WS] PancakeSwap Sync event received")
                    self.process_sync_event(result['data'])
                
        except Exception as e:
            print(f"[BSC WS] Error processing message: {e}")

    def process_sync_event(self, data):
        try:
            # Remove '0x' prefix and decode the data
            data = data[2:]  # Remove '0x'
            reserve0 = int(data[:64], 16)
            reserve1 = int(data[64:128], 16)
            
            token0 = self.pair_contract.functions.token0().call()
            bnb_first = token0.lower() == self.WBNB_ADDRESS.lower()
            
            reserve_bnb = reserve0 if bnb_first else reserve1
            reserve_usdt = reserve1 if bnb_first else reserve0
            
            price = (reserve_usdt / (10 ** 18)) / (reserve_bnb / (10 ** 18))
            with price_lock:
                global latest_pancake_price
                latest_pancake_price = price
                print(f"[PancakeSwap WS] New price: {price}")
            self.check_arbitrage()
        except Exception as e:
            print(f"[BSC WS] Error processing Sync event: {e}")

    def on_message(self, ws, message):
        global latest_binance_price
        self.last_binance_message_time = time.time()
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
            self.start_binance_websocket()

    def on_pong(self, ws, message):
        self.last_binance_message_time = time.time()
        print("[Binance WS] Pong received")

    def on_ping(self, ws, message):
        self.last_binance_message_time = time.time()
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

    def start_binance_websocket(self):
        websocket.enableTrace(False)  # Disable verbose logging
        self.binance_ws = WebSocketApp(
            BINANCE_WS_URL,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
            on_ping=self.on_ping,
            on_pong=self.on_pong
        )
        
        # Start Binance WebSocket with custom settings
        self.binance_ws.run_forever(
            ping_interval=20,
            ping_timeout=10,
            ping_payload='',
            sslopt={"cert_reqs": ssl.CERT_NONE}
        )

    def start_bsc_websocket(self):
        try:
            print("[BSC WS] Starting connection...")
            websocket.enableTrace(True)  # Enable debug logging
            self.bsc_ws = WebSocketApp(
                BSC_WS_URL,
                on_open=self.on_bsc_open,
                on_message=self.on_bsc_message,
                on_error=lambda ws, error: print(f"[BSC WS] Error: {error}"),
                on_close=lambda ws, code, msg: print(f"[BSC WS] Closed: {code} - {msg}")
            )
            
            self.bsc_ws.run_forever(
                ping_interval=20,
                ping_timeout=10,
                sslopt={"cert_reqs": ssl.CERT_NONE}
            )
        except Exception as e:
            print(f"[BSC WS] Connection error: {e}")
            time.sleep(5)
            if self.running:
                self.start_bsc_websocket()

    def connection_monitor(self):
        while self.running:
            current_time = time.time()
            if current_time - self.last_binance_message_time > 30:
                print("[Binance WS] Connection seems dead, restarting...")
                self.binance_ws.close()
                self.start_binance_websocket()
            
            if current_time - self.last_bsc_message_time > 30:
                print("[BSC WS] Connection seems dead, restarting...")
                self.bsc_ws.close()
                self.start_bsc_websocket()
            
            time.sleep(5)

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
        
        self.w3 = self.connect_to_bsc()
        if self.w3 is None:
            raise Exception("Could not establish connection to BSC")
        
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
        global latest_pancake_price
        
        with price_lock:
            binance_price = latest_binance_price
            pancake_price = latest_pancake_price
        

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

    # Modify main() to start both WebSocket connections
    def start(self):
        print("[Main] Starting price monitor...")
        
        # Start BSC WebSocket thread
        bsc_thread = threading.Thread(target=self.start_bsc_websocket)
        bsc_thread.daemon = True
        bsc_thread.start()
        print("[Main] BSC WebSocket thread started")

        # Start Binance WebSocket thread
        binance_thread = threading.Thread(target=self.start_binance_websocket)
        binance_thread.daemon = True
        binance_thread.start()
        print("[Main] Binance WebSocket thread started")

        # Start connection monitor
        monitor_thread = threading.Thread(target=self.connection_monitor)
        monitor_thread.daemon = True
        monitor_thread.start()
        print("[Main] Monitor thread started")

def main():
    monitor = PriceMonitor()
    try:
        monitor.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Main] Shutting down...")
        monitor.running = False
    except Exception as e:
        print(f"[Main] Error: {e}")
        monitor.running = False

if __name__ == "__main__":
    main()