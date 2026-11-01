from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/stock/{ticker}")
def get_stock_data(ticker: str, period: str = "5y"):
    formatted_ticker = ticker.upper()
    stock = yf.Ticker(formatted_ticker)
    
    hist = stock.history(period=period)
    if hist.empty or len(hist) < 10:
        raise HTTPException(status_code=404, detail="Ticker not found or insufficient history.")
        
    hist['Price'] = hist['Close']
    
    q_inc = stock.quarterly_financials
    info = stock.info
    shares = info.get("sharesOutstanding")

    if q_inc.empty or not shares:
        raise HTTPException(status_code=400, detail="Detailed quarterly financials unavailable for this ticker.")

    net_income = None
    for key in ['Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Operation']:
        if key in q_inc.index:
            net_income = q_inc.loc[key]
            break

    if net_income is None:
        raise HTTPException(status_code=400, detail="Could not extract Net Income statements.")

    ttm_df = pd.DataFrame({
        'NetIncome_TTM': net_income.rolling(window=4, min_periods=4).sum()
    }).dropna().sort_index()

    ttm_df['EPS_TTM'] = ttm_df['NetIncome_TTM'] / shares

    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    ttm_df.index = pd.to_datetime(ttm_df.index).tz_localize(None)
    
    combined = pd.merge_asof(hist.sort_index(), ttm_df.sort_index(), left_index=True, right_index=True, direction='backward')
    combined = combined.dropna(subset=['Price', 'EPS_TTM'])
    combined = combined[combined['EPS_TTM'] > 0]

    if len(combined) < 10:
        raise HTTPException(status_code=400, detail="Valid profitable historical data points are too sparse.")

    combined['PE'] = combined['Price'] / combined['EPS_TTM']
    pe_med = float(combined['PE'].median())

    return {
        "dates": combined.index.strftime('%Y-%m-%d').tolist(),
        "price": combined['Price'].tolist(),
        "pe": combined['PE'].tolist(),
        "pe_median": pe_med
    }