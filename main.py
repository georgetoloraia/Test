import ccxt
import pandas as pd
import talib
import time
from config import config

# Initialize Binance API
binance = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.SECRET,
    'enableRateLimit': True,
})

# Function to fetch market data
def fetch_market_data(symbol, timeframe='5m', limit=100):
    ohlcv = binance.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# Function to apply technical indicators
def apply_indicators(df):
    df['rsi'] = talib.RSI(df['close'], timeperiod=14)
    df['sma'] = talib.SMA(df['close'], timeperiod=30)
    df['ema'] = talib.EMA(df['close'], timeperiod=30)
    return df

# Function to identify buy signal
def identify_buy_signal(df):
    # Example condition: RSI below 30 and price crossing above EMA
    if df['rsi'].iloc[-1] < 30 and df['close'].iloc[-1] > df['ema'].iloc[-1]:
        return True
    return False

# Function to place order
def place_order(symbol, side, amount):
    try:
        order = binance.create_order(symbol, 'market', side, amount)
        return order
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

# Function to monitor the price and sell at desired profit
def monitor_and_sell(symbol, buy_price, amount, profit_target=0.05):
    while True:
        df = fetch_market_data(symbol)
        current_price = df['close'].iloc[-1]
        print(f"Current price of {symbol}: {current_price}")

        if current_price >= buy_price * (1 + profit_target):
            sell_order = place_order(symbol, 'sell', amount)
            if sell_order:
                print(f"Sold {amount} of {symbol} at {current_price}")
                break

        time.sleep(60)  # Check price every 1 minute

# Function to execute trade
def execute_trade(symbol, amount, profit_target=0.05):
    buy_order = place_order(symbol, 'buy', amount)
    if buy_order:
        buy_price = binance.fetch_order(buy_order['id'], symbol)['price']
        print(f"Bought {amount} of {symbol} at {buy_price}")
        monitor_and_sell(symbol, buy_price, amount, profit_target)

# Main loop to monitor the market and execute trades
def main():
    while True:
        markets = binance.load_markets()
        usdt_pairs = [symbol for symbol in markets if symbol.endswith('/USDT')]
        
        for symbol in usdt_pairs:
            df = fetch_market_data(symbol)
            df = apply_indicators(df)
            if identify_buy_signal(df):
                execute_trade(symbol, amount=10)  # Adjust amount as needed

        # Check for newly added coins every 5 minutes
        time.sleep(300)

if __name__ == '__main__':
    main()
