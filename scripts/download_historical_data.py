import os
import argparse
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

# Import alpaca-py historical clients
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    raise ValueError("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY in environment.")

def download_historical_data(symbols: list, years_back: int, output_dir: str):
    """
    Downloads historical 1-minute OHLCV bars for given symbols.
    Calculates start and end dates relative to today.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize Alpaca client
    client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    # Calculate time window
    end_date = datetime.now()
    start_date = end_date - relativedelta(years=years_back)
    
    print(f"Downloading data from {start_date.date()} to {end_date.date()} for {symbols}")
    
    # Construct request
    request_params = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Minute,
        start=start_date,
        end=end_date
    )

    try:
        # Fetch the data
        print(f"Requesting data from Alpaca API... this may take a few moments for {years_back} years of 1-minute bars.")
        bars = client.get_stock_bars(request_params)
        df = bars.df
        
        if df.empty:
            print("Warning: Received empty dataframe from Alpaca.")
            return

        # Restructure dataframe (index contains symbol and timestamp usually)
        df = df.reset_index()
        
        # Save individual CSVs per symbol
        for symbol in symbols:
            symbol_df = df[df['symbol'] == symbol].copy()
            symbol_df.sort_values(by='timestamp', inplace=True)
            
            output_file = os.path.join(output_dir, f"{symbol}_1Min_{years_back}Y.csv")
            symbol_df.to_csv(output_file, index=False)
            
            print(f"Saved {len(symbol_df)} records for {symbol} to {output_file}")
            
    except Exception as e:
        print(f"Error fetching data: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical Alpaca data.")
    parser.add_argument("--symbols", type=str, nargs="+", default=["SPY", "QQQ"], help="Symbols to download")
    parser.add_argument("--years", type=int, default=2, help="Years of history to download")
    parser.add_argument("--outdir", type=str, default="data/historical", help="Output directory")
    
    args = parser.parse_args()
    
    download_historical_data(args.symbols, args.years, args.outdir)
