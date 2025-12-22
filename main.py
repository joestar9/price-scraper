import json
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

def scrape_prices(filename="prices.json"):
    print("--- Starting Scraper ---")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        url = "https://bonbast.com/"
        driver.get(url)

        time.sleep(10)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        data_list = []
        seen_keys = set()

        target_ids = {
            "gol18": "Gold Gram 18k",
            "mithqal": "Gold Mithqal",
            "emami": "Coin Emami",
            "azadi": "Coin Azadi",
            "half": "Coin Half",
            "quarter": "Coin Quarter",
            "gram": "Coin Gram",
            "usd": "US Dollar",
            "eur": "Euro"
        }
        
        for element_id, name in target_ids.items():
            try:
                element = soup.find(id=element_id)
                if element:
                    price = element.text.strip()
                    if price and any(c.isdigit() for c in price):
                        data_list.append({
                            "name": name,
                            "price": price,
                            "type": "gold" if "Coin" in name or "Gold" in name else "currency"
                        })
                        seen_keys.add(name)
            except Exception:
                continue

        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                
                if not cols:
                    continue
                
                texts = [c.get_text(strip=True) for c in cols]
                
                if len(texts) >= 4:
                    code = texts[0]
                    name_raw = texts[1]
                    buy_price = texts[-1] 

                    full_name = f"{code} {name_raw}".strip()

                    if full_name in seen_keys or name_raw in seen_keys:
                        continue

                    if not any(c.isdigit() for c in buy_price):
                        continue

                    category = "currency"
                    if "Coin" in name_raw or "Gold" in name_raw:
                        category = "gold"
                    elif code in ["BTC", "ETH", "USDT"]:
                        category = "crypto"

                    data_list.append({
                        "name": full_name,
                        "price": buy_price,
                        "type": category
                    })
                    seen_keys.add(full_name)

        final_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "items": data_list
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, separators=(',', ':'))

        print(f"Success. Items: {len(data_list)}")

    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    scrape_prices()
