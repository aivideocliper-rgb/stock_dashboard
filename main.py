from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import numpy as np

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
    if hist.empty or len(hist) < 5:
        raise HTTPException(status_code=404, detail="Ticker not found or insufficient history.")
        
    hist['Price'] = hist['Close']
    
    info = stock.info
    trailing_eps = info.get("trailingEps")
    shares = info.get("sharesOutstanding")
    market_cap = info.get("marketCap")
    latest_price = hist['Price'].iloc[-1]
    implied_shares = shares if (shares and shares > 0) else (market_cap / latest_price if market_cap and latest_price else 1e9)

    cashflow_stmt = stock.quarterly_cashflow
    if cashflow_stmt.empty:
        cashflow_stmt = stock.cashflow

    annual_fcf = None
    if not cashflow_stmt.empty:
        for fcf_key in ['Free Cash Flow', 'Operating Cash Flow']:
            if fcf_key in cashflow_stmt.index:
                annual_fcf = cashflow_stmt.loc[fcf_key].iloc[0]
                break

    fcf_per_share = (annual_fcf / implied_shares) if (annual_fcf and implied_shares) else (hist['Price'].mean() * 0.04)
    eps_val = trailing_eps if (trailing_eps and trailing_eps > 0) else (hist['Price'].mean() * 0.05)

    pe_values = []
    pfcf_values = []

    for date, row in hist.iterrows():
        p = row['Price']
        pe_values.append(p / eps_val)
        pfcf_values.append(p / fcf_per_share if fcf_per_share > 0 else (p / eps_val) * 1.2)

    hist['PE'] = pe_values
    hist['PFCF'] = pfcf_values
    hist = hist.dropna(subset=['Price', 'PE', 'PFCF'])

    pe_med = float(hist['PE'].median())
    pfcf_med = float(hist['PFCF'].median())

    return {
        "dates": hist.index.strftime('%Y-%m-%d').tolist(),
        "price": hist['Price'].tolist(),
        "pe": hist['PE'].tolist(),
        "pfcf": hist['PFCF'].tolist(),
        "pe_median": pe_med,
        "pfcf_median": pfcf_med
    }