import requests
from bs4 import BeautifulSoup
import re
import json

def get_bist100_wikipedia():
    url = "https://tr.wikipedia.org/wiki/BIST_100"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print("Failed to fetch Wikipedia page:", r.status_code)
            return []
            
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Wikipedia table
        tables = soup.find_all('table', {'class': 'wikitable'})
        print(f"Found {len(tables)} tables")
        
        tickers = []
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]:  # skip header
                cols = row.find_all('td')
                if len(cols) >= 2:
                    # Ticker symbol is usually in the first or second column
                    symbol_text = cols[0].text.strip()
                    # Clean symbol (uppercase, alphabetic letters only, 3-5 chars)
                    symbol = re.sub(r'[^A-Z]', '', symbol_text.upper())
                    if 3 <= len(symbol) <= 5:
                        tickers.append(f"{symbol}.IS")
                        
                    # Also try second column just in case
                    symbol_text_2 = cols[1].text.strip()
                    symbol_2 = re.sub(r'[^A-Z]', '', symbol_text_2.upper())
                    if 3 <= len(symbol_2) <= 5 and symbol_2 != symbol:
                        # If the second col has symbol name
                        pass
        
        # Deduplicate
        tickers = sorted(list(set(tickers)))
        return tickers
    except Exception as e:
        print("Error scraping Wikipedia:", e)
        return []

tickers = get_bist100_wikipedia()
print(f"Extracted {len(tickers)} tickers:")
print(tickers[:15])
