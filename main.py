import pandas as pd
import json
import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

def scrape_bonbast():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    data_list = []
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get("https://bonbast.com/")
        time.sleep(15)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        target_ids = {
            "azadi": "Azadi",
            "emami": "Emami",
            "half": "½ Azadi",
            "quarter": "¼ Azadi",
            "gram": "Gerami",
            "usd": "US Dollar",
            "eur": "Euro",
            "gol18": "Gold Gram 18k",
            "mithqal": "Gold Mithqal"
        }
        
        for element_id, name in target_ids.items():
            element = soup.find(id=element_id)
            if element and element.text.strip():
                data_list.append({"name": name, "price": element.text.strip()})

        seen_names = {item['name'] for item in data_list}
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 4:
                    name_raw = cols[1].get_text(strip=True)
                    price = cols[-1].get_text(strip=True)
                    
                    if name_raw == "Coin Emami": name_raw = "Emami"
                    elif name_raw == "Coin Azadi": name_raw = "Azadi"
                    elif name_raw == "Coin Half": name_raw = "½ Azadi"
                    elif name_raw == "Coin Quarter": name_raw = "¼ Azadi"
                    elif name_raw == "Coin Gram": name_raw = "Gerami"

                    if name_raw not in seen_names and any(c.isdigit() for c in price):
                        data_list.append({"name": name_raw, "price": price})
                        seen_names.add(name_raw)

        return data_list

    except Exception:
        return []
    
    finally:
        if driver:
            driver.quit()

def fetch_crypto(url):
    try:
        df = pd.read_csv(url)
        if 'name' not in df.columns or 'price' not in df.columns:
            return []
        return df[['name', 'price']].to_dict(orient='records')
    except Exception:
        return []

if __name__ == "__main__":
    bonbast_data = scrape_bonbast()
    
    crypto_url = "https://raw.githubusercontent.com/michaelvincentsebastian/Automated-Crypto-Market-Insights/refs/heads/main/latest-data/latest_data.csv"
    crypto_data = fetch_crypto(crypto_url)

    combined_data = bonbast_data + crypto_data

    if combined_data:
        try:
            file_path = os.path.join(os.getcwd(), "merged_prices.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
