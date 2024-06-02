import ccxt
import pandas as pd
import talib
import time
import logging
from config import config
from requests.exceptions import RequestException

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Binance API
binance = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.SECRET,
    'enableRateLimit': True,
})

# Function to fetch market data with retry mechanism
def fetch_market_data(symbol, timeframe='5m', limit=100, max_retries=5):
    for attempt in range(max_retries):
        try:
            ohlcv = binance.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except (ccxt.RequestTimeout, RequestException) as e:
            logging.warning(f"Error fetching market data for {symbol}: {e}. Retrying in {2 ** attempt} seconds...")
            time.sleep(2 ** attempt)
    logging.error(f"Failed to fetch market data for {symbol} after {max_retries} attempts.")
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

# Function to identify sell signal
def identify_sell_signal(df):
    # Example condition: RSI above 70 and MACD crosses below the signal line
    if df['rsi'].iloc[-1] > 70 and df['macd'].iloc[-1] < df['macd_signal'].iloc[-1]:
        return True
    return False

# Function to place order with retry mechanism
def place_order(symbol, side, amount, max_retries=5):
    for attempt in range(max_retries):
        try:
            order = binance.create_order(symbol, 'market', side, amount)
            logging.info(f"Placed {side} order for {amount} of {symbol}")
            return order
        except (ccxt.RequestTimeout, RequestException) as e:
            logging.warning(f"Error placing {side} order for {symbol}: {e}. Retrying in {2 ** attempt} seconds...")
            time.sleep(2 ** attempt)
        except ccxt.InsufficientFunds as e:
            logging.error(f"Insufficient funds to place {side} order for {symbol}: {e}")
            return None
    logging.error(f"Failed to place {side} order for {symbol} after {max_retries} attempts.")
    return None

# Function to monitor the price and sell at desired profit
def monitor_and_sell(symbol, buy_price, amount, profit_target=0.05):
    while True:
        df = fetch_market_data(symbol)
        if df is not None:
            df = apply_indicators(df)  # Apply technical indicators

            current_price = df['close'].iloc[-1]
            logging.info(f"Current price of {symbol}: {current_price}")

            # Condition to sell: price has increased by profit_target or a sell signal based on indicators
            if current_price >= buy_price * (1 + profit_target):
                sell_order = place_order(symbol, 'sell', amount)
                if sell_order:
                    logging.info(f"Sold {amount} of {symbol} at {current_price}")
                    break

            # Example sell condition: RSI above 70 and MACD crosses below the signal line
            if identify_sell_signal(df):
                sell_order = place_order(symbol, 'sell', amount)
                if sell_order:
                    logging.info(f"Sold {amount} of {symbol} at {current_price} based on sell signal")
                    break

        time.sleep(60)  # Check price every 1 minute

# Function to fetch USDT balance with retry mechanism
def fetch_usdt_balance(max_retries=5):
    for attempt in range(max_retries):
        try:
            balance = binance.fetch_balance()
            usdt_balance = balance['total']['USDT']
            logging.info(f"USDT Balance: {usdt_balance}")
            return usdt_balance
        except (ccxt.RequestTimeout, RequestException) as e:
            logging.warning(f"Error fetching USDT balance: {e}. Retrying in {2 ** attempt} seconds...")
            time.sleep(2 ** attempt)
    logging.error(f"Failed to fetch USDT balance after {max_retries} attempts.")
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

# Function to check for newly added coins
def check_new_coins(existing_symbols, current_time, max_retries=5):
    for attempt in range(max_retries):
        try:
            new_coins = binance.fetch_markets()
            for coin in new_coins:
                if coin['symbol'] not in existing_symbols and coin['active'] and 'USDT' in coin['quote']:
                    logging.info(f"New coin detected: {coin['symbol']}")
                    execute_trade(coin['symbol'], profit_target=0.05)
            return
        except (ccxt.RequestTimeout, RequestException) as e:
            logging.warning(f"Error checking for new coins: {e}. Retrying in {2 ** attempt} seconds...")
            time.sleep(2 ** attempt)
    logging.error(f"Failed to check for new coins after {max_retries} attempts.")

# Main function to run the trading bot
def main():
    while True:
        markets = binance.load_markets()
        usdt_pairs = [symbol for symbol in markets if symbol.endswith('/USDT')]
        existing_symbols = set(usdt_pairs)

        # Check for newly added coins every 5 minutes
        current_time = time.time()
        check_new_coins(existing_symbols, current_time)

        # Apply TA-Lib indicators to each pair and decide to buy or sell
        for symbol in usdt_pairs:
            df = fetch_market_data(symbol)
            if df is not None:
                df = apply_indicators(df)
                if identify_buy_signal(df):
                    execute_trade(symbol, profit_target=0.05)  # Adjust profit target as needed
                elif identify_sell_signal(df):
                    amount = fetch_usdt_balance()  # Fetch the total USDT balance for selling
                    if amount > 1:  # Adjust as needed to avoid dust trades
                        sell_order = place_order(symbol, 'sell', amount)
                        if sell_order:
                            logging.info(f"Sold {amount} of {symbol} based on sell signal")

        logging.info("Sleeping for 5 minutes before the next check...")
        time.sleep(300)

if __name__ == '__main__':
    main()
