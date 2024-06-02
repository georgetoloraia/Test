import ccxt
import pandas as pd
import talib
import time
import logging
from config import config

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Binance API
binance = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.SECRET,
    'enableRateLimit': True,
})

# Function to fetch market data
def fetch_market_data(symbol, timeframe='5m', limit=100):
    try:
        ohlcv = binance.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logging.error(f"Error fetching market data for {symbol}: {e}")
        return None

# Function to apply technical indicators
def apply_indicators(df):
    df['rsi'] = talib.RSI(df['close'], timeperiod=14)
    df['macd'], df['macd_signal'], df['macd_hist'] = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
    df['sma'] = talib.SMA(df['close'], timeperiod=30)
    df['ema'] = talib.EMA(df['close'], timeperiod=30)
    return df

# Function to identify buy signal
def identify_buy_signal(df):
    # Example condition: RSI below 30, MACD crosses above signal line, and price above EMA
    if df['rsi'].iloc[-1] < 30 and df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] and df['close'].iloc[-1] > df['ema'].iloc[-1]:
        return True
    return False

# Function to place order
def place_order(symbol, side, amount):
    try:
        order = binance.create_order(symbol, 'market', side, amount)
        logging.info(f"Placed {side} order for {amount} of {symbol}")
        return order
    except Exception as e:
        logging.error(f"Error placing {side} order for {symbol}: {e}")
        return None

# Function to monitor the price and sell at desired profit
def monitor_and_sell(symbol, buy_price, amount, profit_target=0.05):
    while True:
        df = fetch_market_data(symbol)
        if df is not None:
            current_price = df['close'].iloc[-1]
            logging.info(f"Current price of {symbol}: {current_price}")

            if current_price >= buy_price * (1 + profit_target):
                sell_order = place_order(symbol, 'sell', amount)
                if sell_order:
                    logging.info(f"Sold {amount} of {symbol} at {current_price}")
                    break

        time.sleep(60)  # Check price every 1 minute

# Function to fetch USDT balance
def fetch_usdt_balance():
    try:
        balance = binance.fetch_balance()
        usdt_balance = balance['total']['USDT']
        logging.info(f"USDT Balance: {usdt_balance}")
        return usdt_balance
    except Exception as e:
        logging.error(f"Error fetching USDT balance: {e}")
        return 0

# Function to execute trade
def execute_trade(symbol, profit_target=0.05):
    amount = fetch_usdt_balance()  # Fetch the total USDT balance
    if amount > 10:  # Adjust as needed to avoid dust trades
        buy_order = place_order(symbol, 'buy', amount)
        if buy_order:
            buy_price = float(buy_order['info']['fills'][0]['price'])
            logging.info(f"Bought {amount} of {symbol} at {buy_price}")
            monitor_and_sell(symbol, buy_price, amount, profit_target)
    else:
        logging.info("Insufficient USDT balance to execute trade")

# Main loop to monitor the market and execute trades
def main():
    while True:
        markets = binance.load_markets()
        usdt_pairs = [symbol for symbol in markets if symbol.endswith('/USDT')]
        
        # Check for newly added coins every 5 minutes
        new_coins = binance.fetch_markets()
        current_time = time.time()

        for symbol in usdt_pairs:
            df = fetch_market_data(symbol)
            if df is not None:
                df = apply_indicators(df)
                if identify_buy_signal(df):
                    execute_trade(symbol, profit_target=0.05)  # Adjust profit target as needed
        
        for coin in new_coins:
            if coin['active'] and 'USDT' in coin['quote']:
                symbol = coin['symbol']
                if (current_time - coin['info']['listed_at']) <= 300:
                    logging.info(f"New coin detected: {symbol}")
                    execute_trade(symbol, profit_target=0.05)

        logging.info("Sleeping for 5 minutes before the next check...")
        time.sleep(300)

if __name__ == '__main__':
    main()
