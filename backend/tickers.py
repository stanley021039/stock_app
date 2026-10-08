"""Curated starter universe of Taiwan + US tickers.

This is the seed list loaded on first init. Users can add more symbols at
runtime through the "add symbol" API / update button, so this list only needs
to cover the common indices and popular stocks.

Yahoo Finance symbol conventions used here:
  - Taiwan listed (TWSE):   <code>.TW    e.g. 2330.TW
  - Taiwan OTC (TPEx):      <code>.TWO   e.g. 5483.TWO
  - US:                     plain ticker e.g. AAPL
  - Indices:                ^<code>      e.g. ^TWII, ^GSPC
"""

# Each entry: (symbol, name, market, type)
#   market: "TW" | "US"
#   type:   "index" | "stock" | "etf"

INDICES = [
    ("^TWII", "台灣加權指數 (TAIEX)", "TW", "index"),
    ("^GSPC", "S&P 500", "US", "index"),
    ("^IXIC", "Nasdaq Composite", "US", "index"),
    ("^DJI", "Dow Jones Industrial", "US", "index"),
    ("^SOX", "PHLX Semiconductor", "US", "index"),
    ("^RUT", "Russell 2000", "US", "index"),
]

# Indices shown by default on the home page (editable at runtime).
DEFAULT_HOME_INDICES = ["^TWII", "^GSPC", "^IXIC", "^DJI"]

TW_STOCKS = [
    ("2330.TW", "台積電 TSMC", "TW", "stock"),
    ("2317.TW", "鴻海 Hon Hai", "TW", "stock"),
    ("2454.TW", "聯發科 MediaTek", "TW", "stock"),
    ("2308.TW", "台達電 Delta", "TW", "stock"),
    ("2303.TW", "聯電 UMC", "TW", "stock"),
    ("3711.TW", "日月光投控 ASE", "TW", "stock"),
    ("2379.TW", "瑞昱 Realtek", "TW", "stock"),
    ("3034.TW", "聯詠 Novatek", "TW", "stock"),
    ("2382.TW", "廣達 Quanta", "TW", "stock"),
    ("2357.TW", "華碩 ASUS", "TW", "stock"),
    ("4938.TW", "和碩 Pegatron", "TW", "stock"),
    ("3231.TW", "緯創 Wistron", "TW", "stock"),
    ("6669.TW", "緯穎 Wiwynn", "TW", "stock"),
    ("2395.TW", "研華 Advantech", "TW", "stock"),
    ("3008.TW", "大立光 Largan", "TW", "stock"),
    ("2412.TW", "中華電 Chunghwa Telecom", "TW", "stock"),
    ("3045.TW", "台灣大 Taiwan Mobile", "TW", "stock"),
    ("4904.TW", "遠傳 FET", "TW", "stock"),
    ("2882.TW", "國泰金 Cathay FHC", "TW", "stock"),
    ("2881.TW", "富邦金 Fubon FHC", "TW", "stock"),
    ("2891.TW", "中信金 CTBC FHC", "TW", "stock"),
    ("2886.TW", "兆豐金 Mega FHC", "TW", "stock"),
    ("2884.TW", "玉山金 E.SUN FHC", "TW", "stock"),
    ("5880.TW", "合庫金 Taiwan Coop FHC", "TW", "stock"),
    ("1301.TW", "台塑 Formosa Plastics", "TW", "stock"),
    ("1303.TW", "南亞 Nan Ya", "TW", "stock"),
    ("6505.TW", "台塑化 FPCC", "TW", "stock"),
    ("2002.TW", "中鋼 China Steel", "TW", "stock"),
    ("1216.TW", "統一 Uni-President", "TW", "stock"),
    ("2912.TW", "統一超 President Chain", "TW", "stock"),
    ("2207.TW", "和泰車 Hotai Motor", "TW", "stock"),
    ("2603.TW", "長榮 Evergreen Marine", "TW", "stock"),
    ("2609.TW", "陽明 Yang Ming", "TW", "stock"),
    ("2615.TW", "萬海 Wan Hai", "TW", "stock"),
    ("0050.TW", "元大台灣50 ETF", "TW", "etf"),
    ("0056.TW", "元大高股息 ETF", "TW", "etf"),
    ("006208.TW", "富邦台50 ETF", "TW", "etf"),
    ("00878.TW", "國泰永續高股息 ETF", "TW", "etf"),
]

US_STOCKS = [
    ("AAPL", "Apple", "US", "stock"),
    ("MSFT", "Microsoft", "US", "stock"),
    ("GOOGL", "Alphabet (Google)", "US", "stock"),
    ("AMZN", "Amazon", "US", "stock"),
    ("META", "Meta Platforms", "US", "stock"),
    ("NVDA", "NVIDIA", "US", "stock"),
    ("TSLA", "Tesla", "US", "stock"),
    ("AVGO", "Broadcom", "US", "stock"),
    ("AMD", "AMD", "US", "stock"),
    ("INTC", "Intel", "US", "stock"),
    ("NFLX", "Netflix", "US", "stock"),
    ("ADBE", "Adobe", "US", "stock"),
    ("CRM", "Salesforce", "US", "stock"),
    ("ORCL", "Oracle", "US", "stock"),
    ("CSCO", "Cisco", "US", "stock"),
    ("QCOM", "Qualcomm", "US", "stock"),
    ("TXN", "Texas Instruments", "US", "stock"),
    ("MU", "Micron", "US", "stock"),
    ("TSM", "TSMC ADR", "US", "stock"),
    ("JPM", "JPMorgan Chase", "US", "stock"),
    ("BAC", "Bank of America", "US", "stock"),
    ("V", "Visa", "US", "stock"),
    ("MA", "Mastercard", "US", "stock"),
    ("BRK-B", "Berkshire Hathaway B", "US", "stock"),
    ("WMT", "Walmart", "US", "stock"),
    ("KO", "Coca-Cola", "US", "stock"),
    ("PEP", "PepsiCo", "US", "stock"),
    ("DIS", "Walt Disney", "US", "stock"),
    ("NKE", "Nike", "US", "stock"),
    ("MCD", "McDonald's", "US", "stock"),
    ("COST", "Costco", "US", "stock"),
    ("JNJ", "Johnson & Johnson", "US", "stock"),
    ("UNH", "UnitedHealth", "US", "stock"),
    ("PFE", "Pfizer", "US", "stock"),
    ("XOM", "Exxon Mobil", "US", "stock"),
    ("CVX", "Chevron", "US", "stock"),
    ("BA", "Boeing", "US", "stock"),
    ("SPY", "SPDR S&P 500 ETF", "US", "etf"),
    ("QQQ", "Invesco QQQ ETF", "US", "etf"),
    ("VOO", "Vanguard S&P 500 ETF", "US", "etf"),
    ("DIA", "SPDR Dow Jones ETF", "US", "etf"),
    ("IWM", "iShares Russell 2000 ETF", "US", "etf"),
]


def all_seed_symbols():
    """Return the full seed list as a list of dicts."""
    rows = []
    for symbol, name, market, typ in INDICES + TW_STOCKS + US_STOCKS:
        rows.append(
            {"symbol": symbol, "name": name, "market": market, "type": typ}
        )
    return rows
