import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime
import sys
import traceback

def main():
    try:
        print("Authenticating with Google Cloud...")
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

        # Ensure valid credentials.json is maintained in the active execution directory
        credentials = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(credentials)

        print("Connecting to Google Sheet...")
        sheet = client.open("Daily Market Data").sheet1

        tickers = ['TSLA', 'NVDA', 'AAPL', 'MSFT', 'AMZN', 'GOOG', 'META']
        data_rows = []

        # Generate execution timestamp for batch payload identification
        run_date = datetime.now().strftime('%m/%d/%y')
        print(f"Fetching live market data for {len(tickers)} tickers. This takes a few seconds...\n")

        # Execute data extraction sequence with verbose tracing
        for ticker in tickers:
            print(f"  -> Pulling data for {ticker}...")
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1y")
                
                if len(hist) < 2:
                    print(f"  [!] Warning: Not enough historical data found for {ticker}.")
                    continue
                
                # Force explicit float casting to prevent numpy datatype segfaults
                current_price = float(hist['Close'].iloc[-1])
                previous_price = float(hist['Close'].iloc[-2])
                
                dollar_change = current_price - previous_price
                percent_change = (dollar_change / previous_price) * 100
                
                high_52w = float(hist['High'].max())
                high_date = hist['High'].idxmax().strftime('%m/%d/%Y')
                
                cost_of_25 = current_price * 25
                profit_25 = (high_52w * 25) - cost_of_25
                
                upside_raw = (high_52w - current_price) / current_price
                
                data_rows.append([
                    "", ticker, current_price, percent_change, dollar_change, 
                    high_52w, high_date, cost_of_25, profit_25, upside_raw
                ])
                print(f"  -> {ticker} successfully processed.")
                
            except Exception as e:
                print(f"  [X] Data processing exception encountered for {ticker}: {e}")
                continue

        # Check if batch completely failed before processing
        if not data_rows:
            print("\n[!] CRITICAL: No data was successfully fetched for any tickers. Aborting Google Sheets update.")
            return

        print("\nFormatting data payload...")
        
        # Construct operational DataFrame utilizing standardized target schema
        df = pd.DataFrame(data_rows, columns=[
            'Date of Data Refresh', 'Stock Symbol', 'Closing Price', 'Daily Change (%)', 'Daily Change ($)',
            '52-Week High', 'Date High Reached', 'Cost of 25 shares', 'Expected Profit', 'Upside Potential'
        ])

        # Sort dataset against primary performance metrics in descending sequence
        df = df.sort_values(by='Upside Potential', ascending=False)

        # Defensive formatting functions
        def format_currency(x): 
            return f"${float(x):.2f}" if pd.notna(x) else "---"
            
        def format_pct(x): 
            return f"{float(x) * 100:.2f}%" if pd.notna(x) else "---"

        def format_dollar_change(x):
            if pd.isna(x): return "'$0.00"
            val = float(x)
            if val > 0: return f"'+${val:.2f}"
            if val < 0: return f"'-${abs(val):.2f}"
            return "'$0.00"

        def format_arrow_pct(x):
            if pd.isna(x): return "'0.00%"
            val = float(x)
            if val > 0: return f"'↑{val:.2f}%"
            if val < 0: return f"'↓{abs(val):.2f}%"
            return "'0.00%"

        # Apply formatting safely across columns
        df['Closing Price'] = df['Closing Price'].apply(format_currency)
        df['52-Week High'] = df['52-Week High'].apply(format_currency)
        df['Cost of 25 shares'] = df['Cost of 25 shares'].apply(format_currency)
        df['Expected Profit'] = df['Expected Profit'].apply(format_currency)
        df['Upside Potential'] = df['Upside Potential'].apply(format_pct)

        # Enforce string formatting with apostrophes and specific Unicode arrows
        df['Daily Change ($)'] = df['Daily Change ($)'].apply(format_dollar_change)
        df['Daily Change (%)'] = df['Daily Change (%)'].apply(format_arrow_pct)

        final_values = df.values.tolist()

        # Compile API insertion payload containing operational buffers
        separator_row = [f"{run_date}", "", "", "", "", "", "", "", "", ""]
        blank_row = ["", "", "", "", "", "", "", "", "", ""]

        final_batch = [separator_row] + final_values + [blank_row]

        print("Pushing data to Google Sheets...")

        # Execute insertion operation at chronological vertex (Row 2)
        sheet.insert_rows(final_batch, 2, value_input_option='USER_ENTERED')
        print("✅ Success! Your Google Sheet has been updated.")

    except Exception as e:
        # Master error catcher prevents silent terminal exits
        print("\n" + "="*60)
        print("CRITICAL SCRIPT FAILURE")
        print("="*60)
        print(traceback.format_exc())
        print("="*60)

if __name__ == "__main__":
    main()