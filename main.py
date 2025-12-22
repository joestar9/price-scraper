import json
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

def scrape_prices(filename="prices.json"):
    print("--- Starting Optimized Scraper ---")
    start_time = time.time()
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    
    # --- بهینه سازی ۱: بلاک کردن عکس ها و CSS ---
    prefs = {
        "profile.managed_default_content_settings.images": 2, # عکس لود نشود
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.cookies": 2,
        "profile.managed_default_content_settings.javascript": 1, # جاوااسکریپت روشن بماند
        "profile.managed_default_content_settings.plugins": 1,
        "profile.managed_default_content_settings.popups": 2,
        "profile.managed_default_content_settings.geolocation": 2,
        "profile.managed_default_content_settings.media_stream": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        url = "https://bonbast.com/"
        driver.get(url)

        # --- بهینه سازی ۲: ویت هوشمند به جای اسلیپ ثابت ---
        # حداکثر ۱۵ ثانیه صبر میکند، اما به محض لود شدن عنصر ادامه میدهد
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "gol18"))
            )
            print("Page loaded successfully.")
        except:
            print("Timeout waiting for page load, trying to parse anyway...")

        # پارس کردن دیتا (بدون تغییر)
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
            element = soup.find(id=element_id)
            if element:
                price = element.text.strip()
                if price and any(c.isdigit() for c in price):
                    data_list.append({"name": name, "price": price, "type": "gold" if "Coin" in name or "Gold" in name else "currency"})
                    seen_keys.add(name)

        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue
                texts = [c.get_text(strip=True) for c in cols]
                if len(texts) >= 4:
                    code, name_raw, buy_price = texts[0], texts[1], texts[-1]
                    full_name = f"{code} {name_raw}".strip()
                    if full_name in seen_keys or name_raw in seen_keys or not any(c.isdigit() for c in buy_price): continue
                    
                    category = "currency"
                    if "Coin" in name_raw or "Gold" in name_raw: category = "gold"
                    elif code in ["BTC", "ETH", "USDT"]: category = "crypto"

                    data_list.append({"name": full_name, "price": buy_price, "type": category})
                    seen_keys.add(full_name)

        final_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "execution_time": round(time.time() - start_time, 2), # زمان اجرا
            "items": data_list
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, separators=(',', ':'))

        print(f"Done in {final_data['execution_time']} seconds. Items: {len(data_list)}")

    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    scrape_prices()
