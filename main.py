import time
import warnings

import requests
from web3 import Web3

warnings.filterwarnings('ignore', message='.*OpenSSL.*')

# Binance API endpoint
BINANCE_API = "https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT"

# BSC RPC endpoint
BSC_RPC = "https://bsc-dataseed.binance.org/"  # Public BSC node

def connect_to_bsc():
    try:
        # Initialize web3 with BSC node
        w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        
        # Check connection
        if w3.is_connected():
            print("Successfully connected to BSC")
            return w3
        else:
            print("Failed to connect to BSC")
            return None
    except Exception as e:
        print(f"Error connecting to BSC: {str(e)}")
        return None

# Initialize connection before using
w3 = connect_to_bsc()

if w3 is None:
    print("Could not establish connection to BSC. Exiting...")
    exit(1)

# Update these addresses
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"  # WBNB on BSC
USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"  # USDT on BSC
PANCAKE_PAIR_ADDRESS = "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE"  # PancakeSwap BNB/USDT pair

# Token decimals
BNB_DECIMALS = 18
USDT_DECIMALS = 18

# UniswapV2 Pair ABI (simplified for reserve fetching)
UNISWAP_PAIR_ABI = [
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

# Only initialize contract after successful connection
pair_contract = w3.eth.contract(address=w3.to_checksum_address(PANCAKE_PAIR_ADDRESS), abi=UNISWAP_PAIR_ABI)

def get_binance_price():
    try:
        response = requests.get(BINANCE_API)
        print(f"[get_binance_price] response {response.json()}")
        return float(response.json()['price'])
    except Exception as e:
        print(f"[Binance Error] {e}")
        return None

def get_pancake_price():
    try:
        # First, verify connection to BSC
        if not w3.is_connected():
            print("[Pancake Error] Not connected to BSC")
            return None

        # Get reserves
        reserves = pair_contract.functions.getReserves().call()
        token0 = pair_contract.functions.token0().call()
        
        print(f"[Debug] Token0 address: {token0}")
        print(f"[Debug] Reserves: {reserves}")

        # Identify token order
        bnb_first = token0.lower() == WBNB_ADDRESS.lower()

        reserve_bnb = reserves[0] if bnb_first else reserves[1]
        reserve_usdt = reserves[1] if bnb_first else reserves[0]

        print(f"[Debug] BNB reserve: {reserve_bnb}")
        print(f"[Debug] USDT reserve: {reserve_usdt}")

        # Price = USDT / BNB
        price = (reserve_usdt / (10 ** USDT_DECIMALS)) / (reserve_bnb / (10 ** BNB_DECIMALS))
        print(f"[Debug] Calculated price: {price}")
        return price
    except Exception as e:
        print(f"[Pancake Error] {str(e)}")
        return None

def detect_arbitrage(threshold_pct=0.5):
    binance_price = get_binance_price()
    pancake_price = get_pancake_price()

    if binance_price is None or pancake_price is None:
        print("Price fetch failed.")
        return

    diff = binance_price - pancake_price
    diff_pct = (diff / pancake_price) * 100

    print(f"[BNB] Binance: {binance_price:.3f} | PancakeSwap: {pancake_price:.3f} | Diff: {diff_pct:.2f}%")

    if abs(diff_pct) >= threshold_pct:
        if diff > 0:
            print(f"⚡ Arbitrage Opportunity: Buy on PancakeSwap, Sell on Binance (+{diff_pct:.2f}%)")
        else:
            print(f"⚡ Arbitrage Opportunity: Buy on Binance, Sell on PancakeSwap (+{-diff_pct:.2f}%)")

if __name__ == "__main__":
    # Add this check before running the main loop
    if not w3.is_connected():
        print("Not connected to BSC")
    else:
        print("Successfully connected to BSC")
    while True:
        # get_binance_price()
        detect_arbitrage(threshold_pct=0.5)
        time.sleep(10)  # Poll every 10 seconds