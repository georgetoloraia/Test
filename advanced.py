import ccxt.async_support as ccxt
import asyncio
import logging
import pandas as pd
import talib
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Initialize Binance exchange connection
exchange = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.SECRET,
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True}
})

# Parameters
quote_currency = 'USDT'
initial_investment = 5.0  # USD
rsi_period = 14  # User's RSI period
commission_rate = 0.001  # 0.1%
stop_loss_percentage = 0.05  # 5% stop loss
take_profit_percentage = 0.1  # 10% take profit

# Fetch all tradeable pairs
async def get_tradeable_pairs(quote_currency):
    try:
        await exchange.load_markets()
        return [symbol for symbol in exchange.symbols if quote_currency in symbol.split('/')]
    except Exception as e:
        logger.error(f"Error loading markets: {e}")
        return []

# Close exchange connection
async def close_exchange():
    if hasattr(exchange, 'close'):
        await exchange.close()

# Preprocess data
def preprocess_data(df):
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_columns):
        raise ValueError("DataFrame must contain open, high, low, close, and volume columns")
    df = df.ffill().bfill()
    return df

# Fetch historical prices
async def fetch_historical_prices(pair, timeframe='15m', limit=100):
    try:
        ohlcv = await exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
        if ohlcv is None or len(ohlcv) == 0:
            logger.info(f"No data returned for {pair}.")
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = preprocess_data(df)

        df['ema'] = talib.EMA(df['close'], timeperiod=14)
        df['wma'] = talib.WMA(df['close'], timeperiod=14)
        df['upper_band'], df['middle_band'], df['lower_band'] = talib.BBANDS(df['close'], timeperiod=20, nbdevup=2, nbdevdn=2)
        df['trix'] = talib.TRIX(df['close'], timeperiod=15)
        df['rsi'] = talib.RSI(df['close'], timeperiod=14)
        df['macd'], df['macd_signal'], df['macd_hist'] = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
        df['slowk'], df['slowd'] = talib.STOCH(df['high'], df['low'], df['close'], fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        df['cci'] = talib.CCI(df['high'], df['low'], df['close'], timeperiod=14)
        df['obv'] = talib.OBV(df['close'], df['volume'])

        return df
    except Exception as e:
        logger.error(f"Error fetching historical prices for {pair}: {e}")
        return pd.DataFrame()

# Evaluate trading signals
def advanced_evaluate_trading_signals(df):
    if df.empty:
        logger.info("DataFrame is empty.")
        return False, None

    latest = df.iloc[-1]

    # Buy conditions
    buy_conditions = [
        latest['close'] > latest['ema'],  # Price above EMA
        latest['close'] > latest['wma'],  # Price above WMA
        latest['trix'] > 0,  # TRIX positive
        latest['close'] < latest['lower_band'],  # Price below lower Bollinger Band
        latest['rsi'] < 30,  # RSI below 30 (oversold)
        latest['macd'] > latest['macd_signal'],  # MACD above signal line
        latest['cci'] < -100,  # CCI below -100 (oversold)
        latest['slowk'] < 20 and latest['slowd'] < 20  # Stochastic below 20 (oversold)
    ]

    # Sell conditions
    sell_conditions = [
        latest['close'] < latest['ema'],  # Price below EMA
        latest['close'] < latest['wma'],  # Price below WMA
        latest['trix'] < 0,  # TRIX negative
        latest['close'] > latest['upper_band'],  # Price above upper Bollinger Band
        latest['rsi'] > 70,  # RSI above 70 (overbought)
        latest['macd'] < latest['macd_signal'],  # MACD below signal line
        latest['cci'] > 100,  # CCI above 100 (overbought)
        latest['slowk'] > 80 and latest['slowd'] > 80  # Stochastic above 80 (overbought)
    ]

    if all(buy_conditions):
        logger.info(f"Buy signal conditions met: {dict(zip(['ema', 'wma', 'trix', 'close < Lower Band', 'rsi', 'macd', 'cci', 'stoch'], buy_conditions))}")
        return True, 'buy'
    elif all(sell_conditions):
        logger.info(f"Sell signal conditions met: {dict(zip(['ema', 'wma', 'trix', 'close > Upper Band', 'rsi', 'macd', 'cci', 'stoch'], sell_conditions))}")
        return True, 'sell'
    return False, None

# Get balance
async def get_balance(currency):
    try:
        balance = await exchange.fetch_balance()
        available_balance = balance['free'][currency]
        logger.info(f"Available balance for {currency}: {available_balance}")
        return available_balance
    except Exception as e:
        logger.error(f"Error fetching balance for {currency}: {e}")
        return 0

# Get current price
async def get_current_price(pair):
    try:
        ticker = await exchange.fetch_ticker(pair)
        current_price = ticker['last']
        logger.info(f"Current market price for {pair}: {current_price}")
        return current_price
    except Exception as e:
        logger.error(f"Error fetching current price for {pair}: {e}")
        return None

# Place market order
async def place_market_order(pair, side, amount):
    if amount <= 0:
        logger.error(f"Invalid amount for {side} order: {amount}")
        return None
    try:
        if side == 'buy':
            order = await exchange.create_market_buy_order(pair, amount)
        elif side == 'sell':
            order = await exchange.create_market_sell_order(pair, amount)
        logger.info(f"Market {side} order placed for {pair}: {amount} units at market price.")
        return order
    except Exception as e:
        logger.error(f"An error occurred placing a {side} order for {pair}: {e}")
        return None

# Convert to USDT
async def convert_to_usdt(pair):
    try:
        asset = pair.split('/')[0]
        asset_balance = await get_balance(asset)
        if asset_balance > 0:
            order_result = await place_market_order(pair, 'sell', asset_balance)
            if order_result:
                logger.info(f"Converted {asset_balance} of {asset} to USDT")
                return order_result
        else:
            logger.info(f"No {asset} balance to convert to USDT")
    except Exception as e:
        logger.error(f"An error occurred converting {pair} to USDT: {e}")
    return None

# Main trading logic with stop-loss and take-profit
async def advanced_trade():
    pairs = await get_tradeable_pairs('USDT')
    while True:
        try:
            for pair in pairs:
                logger.info(f"Processing pair: {pair}")
                historical_data = await fetch_historical_prices(pair)
                signal, action = advanced_evaluate_trading_signals(historical_data)
                if signal:
                    usdt_balance = await get_balance('USDT')
                    if action == 'buy' and usdt_balance > initial_investment:
                        amount_to_buy = (usdt_balance * (1 - commission_rate)) / historical_data['close'].iloc[-1]
                        buy_order = await place_market_order(pair, 'buy', amount_to_buy)
                        if buy_order:
                            buy_price = buy_order['price']
                            # Monitor position for stop-loss or take-profit
                            while True:
                                current_price = await get_current_price(pair)
                                if current_price <= buy_price * (1 - stop_loss_percentage):
                                    logger.info(f"Stop-loss triggered for {pair} at {current_price}")
                                    await place_market_order(pair, 'sell', amount_to_buy)
                                    break
                                elif current_price >= buy_price * (1 + take_profit_percentage):
                                    logger.info(f"Take-profit triggered for {pair} at {current_price}")
                                    await place_market_order(pair, 'sell', amount_to_buy)
                                    break
                                await asyncio.sleep(60)  # Check every minute
                    elif action == 'sell':
                        asset = pair.split('/')[0]
                        asset_balance = await get_balance(asset)
                        if asset_balance > 0:
                            await place_market_order(pair, 'sell', asset_balance)
                            await convert_to_usdt(pair)
                await asyncio.sleep(1)  # Short delay to prevent hitting rate limits
        except Exception as e:
            logger.error(f"An error occurred during trading: {e}")
            await asyncio.sleep(60)  # Wait for 1 minute before retrying

async def main():
    try:
        await advanced_trade()
    except Exception as e:
        logger.error(f"An error occurred in the main trading loop: {e}")
    finally:
        await close_exchange()
        logger.info("Exchange connection closed.")

if __name__ == "__main__":
    asyncio.run(main())
