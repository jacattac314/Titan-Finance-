import os
import sys
from datetime import datetime, timedelta
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or "PLACEHOLDER" in API_KEY:
    print("Error: Valid ALPACA_API_KEY not found in environment variables.")
    sys.exit(1)

def analyze_portfolio():
    print("--- TitanFlow Daily Portfolio Analysis ---")
    
    # 1. Initialize Client
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    # 2. Define Parameters
    # Using the watchlist from Gateway v1
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "NVDA", "AMD", "AMZN"]
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Fetching data for: {', '.join(symbols)}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    
    request_params = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start_date,
        end=end_date
    )
    
    # 3. Fetch Data
    try:
        bars = client.get_stock_bars(request_params)
        df = bars.df
        
        # Reset index to make symbol a column if multi-index
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index()
            
        print(f"\nSuccessfully retrieved {len(df)} records.")
        
        # 4. Calculate Metrics
        results = []
        for symbol in symbols:
            symbol_data = df[df['symbol'] == symbol].copy()
            if symbol_data.empty:
                continue
                
            symbol_data = symbol_data.sort_values('timestamp')
            
            # Daily Returns
            symbol_data['pct_change'] = symbol_data['close'].pct_change()
            
            # Metrics
            start_price = symbol_data.iloc[0]['close']
            end_price = symbol_data.iloc[-1]['close']
            total_return = ((end_price - start_price) / start_price) * 100
            volatility = symbol_data['pct_change'].std() * 100 # In percentage
            avg_volume = symbol_data['volume'].mean()
            
            results.append({
                "Symbol": symbol,
                "Start Price": f"${start_price:.2f}",
                "End Price": f"${end_price:.2f}",
                "Total Return": f"{total_return:+.2f}%",
                "Volatility (Daily)": f"{volatility:.2f}%",
                "Avg Volume": f"{avg_volume:,.0f}"
            })
            
        # 5. Display Report
        results_df = pd.DataFrame(results)
        print("\n--- Performance Report (Last 30 Days) ---")
        print(results_df.to_string(index=False))
        
    except Exception as e:
        print(f"Error fetching/processing data: {e}")

if __name__ == "__main__":
    analyze_portfolio()
