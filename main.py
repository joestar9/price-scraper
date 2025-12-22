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
    print("--- Starting Bonbast Scraper ---")
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
        
        url = "https://bonbast.com/"
        driver.get(url)

        time.sleep(15)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        top_items = {
            "gol18": "Gold Gram 18k",
            "mithqal": "Gold Mithqal",
            "ounce": "Gold Ounce",
            "ju18": "Gold Gram 18k Jewelry"
        }
        
        for elem_id, name in top_items.items():
            element = soup.find(id=elem_id)
            if element and any(c.isdigit() for c in element.text):
                price = element.text.strip()
                data_list.append({"name": name, "price": price})

        seen_names = {item['name'] for item in data_list}
        
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                
                name = ""
                price = ""
                
                if len(cols) == 4:
                    name = cols[1].get_text(strip=True)
                    price = cols[2].get_text(strip=True)
                
                elif len(cols) == 3:
                    name = cols[0].get_text(strip=True)
                    price = cols[1].get_text(strip=True)

                if name and price and any(c.isdigit() for c in price):
                    if "Emami" in name: name = "Emami"
                    elif "Azadi" in name and "Gera" not in name and "½" not in name and "¼" not in name: name = "Azadi"
                    elif "Half" in name: name = "½ Azadi"
                    elif "Quarter" in name: name = "¼ Azadi"
                    elif "Gram" in name and "Coin" in name: name = "Gerami"
                    
                    if name not in seen_names:
                        data_list.append({"name": name, "price": price})
                        seen_names.add(name)

        return data_list

    except Exception as e:
        print(f"Error scraping Bonbast: {e}")
        return []
    
    finally:
        if driver:
            driver.quit()

def fetch_crypto(url):
    print("--- Starting Crypto Fetcher ---")
    try:
        df = pd.read_csv(url)
        if 'name' not in df.columns or 'price' not in df.columns:
            return []
        
        data = df[['name', 'price']].to_dict(orient='records')
        return data
    except Exception as e:
        print(f"Error fetching crypto: {e}")
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
                json.dump(combined_data, f, ensure_ascii=False, separators=(',', ':'))
            print(f"Successfully saved {len(combined_data)} items.")
        except Exception as e:
            print(f"Failed to save file: {e}")
    else:
        print("No data collected.")
