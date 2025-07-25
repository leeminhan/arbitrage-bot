
# Binance-PancakeSwap Arbitrage Monitor

Real-time price monitoring system for detecting arbitrage opportunities between Binance and PancakeSwap for BNB/USDT pair.

## Technical Design

### Key Components

1. **BSC Connectivity**
   - Web3 connection to Binance Smart Chain
   - PancakeSwap pair contract integration
   - Uses BSC RPC endpoint for blockchain interactions

2. **Price Data Sources**
   - Binance: Real-time WebSocket stream (`bnbusdt@ticker`)
   - PancakeSwap: Smart contract calls to get reserves and calculate price
   - Thread-safe price updates using locks

3. **WebSocket Implementation**
   - Continuous connection to Binance WebSocket API
   - Automatic reconnection mechanism
   - Connection health monitoring
   - Ping/Pong heartbeat (20s interval)

4. **Arbitrage Detection**
   - Configurable threshold (currently 0.5%)
   - Real-time price comparison
   - Bi-directional opportunity detection (Binance ↔ PancakeSwap)

### Data Flow

Binance WS->>Price Monitor: Real-time price updates Price Monitor->>PancakeSwap: Query reserves PancakeSwap-->>Price Monitor: Return current price Price Monitor->>Price Monitor: Compare prices Price Monitor->>Price Monitor: Check arbitrage threshold

### System Features

#### Error Handling
- WebSocket auto-reconnection
- Connection monitoring
- Dead connection detection (30s timeout)
- Price sanity checks
- JSON parsing error handling
- Network error recovery

#### Threading Model
- Main thread: Core application logic
- WebSocket thread: Binance price updates
- Monitor thread: Connection health checking
- Thread synchronization via locks

#### Configuration Parameters
- WebSocket ping interval: 20 seconds
- Connection timeout: 30 seconds
- Arbitrage threshold: 0.5%
- Reconnection delay: 5 seconds

#### Contract Interfaces
- PancakeSwap Pair Contract
  - `getReserves()`: Get token reserves
  - `token0()`: Get first token address
  - Target pair: BNB/USDT

## Requirements

- Python 3.8+
- Web3.py
- Websocket-client

## Setup

1. Install dependencies:
`bash pip install -r requirements.txt`
2. Configure environment variables:
`bash BSC_RPC_URL=your_bsc_node_url PANCAKESWAP_ROUTER=pancakeswap_router_address`
3. Run the monitor:
bash python main.py
