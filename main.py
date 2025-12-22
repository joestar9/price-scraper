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

def scrape_bonbast_data():
    """
    Scrapes currency, gold, and coin data from bonbast.com.
    This function is optimized to run in a headless environment like GitHub Actions.
    
    Returns:
        list: A list of dictionaries, where each dictionary contains the 'name' and 'price'.
              Returns an empty list if an error occurs.
    """
    print("--- Starting Bonbast Scraper ---")
    print("... Initializing Chrome Driver")

    chrome_options = Options()
    # Arguments required for running in a Docker/GitHub Actions environment
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    data_list = []
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        url = "https://bonbast.com/"
        print(f"... Fetching data from {url}")
        driver.get(url)

        # Increased wait time for reliability in automated environments
        time.sleep(10)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # --- Extract data by targeted IDs for primary items ---
        target_ids = {
            "gol18": "Gold Gram 18k", "mithqal": "Gold Mithqal", "emami": "Coin Emami",
            "azadi": "Coin Azadi", "half": "Coin Half", "quarter": "Coin Quarter",
            "gram": "Coin Gram", "usd": "US Dollar", "eur": "Euro"
        }
        
        print("... Extracting Targeted Gold, Coins, and Currencies")
        for element_id, name in target_ids.items():
            element = soup.find(id=element_id)
            if element and element.text.strip() and any(c.isdigit() for c in element.text):
                data_list.append({"name": name, "price": element.text.strip()})

        # --- Extract data from tables for other items ---
        print("... Extracting Main Table Data")
        seen_names = {item['name'] for item in data_list}
        
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 4:
                    name_raw = cols[1].get_text(strip=True)
                    price = cols[-1].get_text(strip=True) # Get the 'buy' price

                    if name_raw not in seen_names and any(c.isdigit() for c in price):
                        data_list.append({"name": name_raw, "price": price})
                        seen_names.add(name_raw)

        print(f"--- Scraped {len(data_list)} items from Bonbast ---")
        return data_list

    except Exception as e:
        print(f"Error occurred during Bonbast scraping: {e}", file=sys.stderr)
        return [] # Return empty list on failure
    
    finally:
        if driver:
            driver.quit()
            print("... Chrome Driver closed.")

def fetch_crypto_data(url):
    """
    Downloads cryptocurrency data from a CSV URL, extracts 'name' and 'price',
    and returns it as a list of dictionaries.
    
    Args:
        url (str): The URL of the CSV file.
    
    Returns:
        list: A list of dictionaries with 'name' and 'price', or an empty list on error.
    """
    print("\n--- Starting Crypto Data Fetcher ---")
    try:
        print(f"... Downloading data from {url}")
        df = pd.read_csv(url)
        
        # Ensure 'name' and 'price' columns exist
        if 'name' not in df.columns or 'price' not in df.columns:
            print("Error: CSV file must contain 'name' and 'price' columns.", file=sys.stderr)
            return []
            
        required_data = df[['name', 'price']]
        data_list = required_data.to_dict(orient='records')
        print(f"--- Fetched {len(data_list)} crypto items ---")
        return data_list

    except Exception as e:
        print(f"An error occurred while fetching crypto data: {e}", file=sys.stderr)
        return []

if __name__ == "__main__":
    # --- Step 1: Scrape data from Bonbast ---
    bonbast_items = scrape_bonbast_data()

    # --- Step 2: Fetch crypto data from CSV URL ---
    crypto_url = "https://raw.githubusercontent.com/michaelvincentsebastian/Automated-Crypto-Market-Insights/refs/heads/main/latest-data/latest_data.csv"
    crypto_items = fetch_crypto_data(crypto_url)

    # --- Step 3: Combine all data ---
    combined_data = bonbast_items + crypto_items

    # --- Step 4: Save the combined data to a single JSON file ---
    output_filename = "merged_prices.json"
    print(f"\n--- Combining and Saving Data ---")
    if combined_data:
        try:
            # Save in the current working directory, which is standard for CI/CD
            file_path = os.path.join(os.getcwd(), output_filename)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, ensure_ascii=False, indent=4)
            
            print(f"Successfully saved {len(combined_data)} items to {file_path}")
        except Exception as e:
            print(f"Failed to save JSON file: {e}", file=sys.stderr)
    else:
        print("No data was collected, skipping file creation.", file=sys.stderr)

    print("--- Script finished ---")

