#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bonbast + Crypto -> rates_v2_latest generator

Goals:
- Keep your existing JSON schema (and future fields like aliases/inputMode/lists/schemaVersion) intact.
- Update only numeric fields (price/usdPrice/change24h) + fetchedAtMs/source.
- Be fast & cheap in CI:
  * Prefer plain HTTP fetch + BeautifulSoup parse
  * Fallback to Selenium only if needed (optional)

Output: rates_v2_latest (minified JSON, UTF-8, stable key order from template)
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from bs4 import BeautifulSoup

# Optional Selenium fallback (only used if HTTP fetch doesn't return enough data)
USE_SELENIUM_FALLBACK = True
SELENIUM_WAIT_SECONDS = 12  # lower == cheaper CI

BONBAST_URL = "https://bonbast.com/"
CRYPTO_CSV_URL = (
    "https://raw.githubusercontent.com/michaelvincentsebastian/"
    "Automated-Crypto-Market-Insights/refs/heads/main/latest-data/latest_data.csv"
)

# Use the same filename your Worker expects / you commit to GitHub
OUTPUT_FILE = "rates_v2_latest"
# Template file: your repo should already contain a baseline JSON with metadata
TEMPLATE_FILE = "rates_v2_latest"  # read current committed file and update it

# KV-side keys are unrelated here; this is the generator that creates the GitHub file.


# ---------------------------
# Helpers: digits & numbers
# ---------------------------

_PERSIAN_ARABIC_DIGITS = str.maketrans({
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})

_num_re = re.compile(r"[0-9]+")


def to_int_price(text: str) -> Optional[int]:
    """
    Extract integer price from a text, handling commas and Persian/Arabic digits.
    Returns None if no digits found.
    """
    if not text:
        return None
    t = text.translate(_PERSIAN_ARABIC_DIGITS)
    m = _num_re.findall(t)
    if not m:
        return None
    # join all digit groups (handles commas/spaces)
    try:
        return int("".join(m))
    except Exception:
        return None


def norm_key(s: str) -> str:
    """Normalize names for matching (titles, csv names, etc.)."""
    s = (s or "").strip().lower()
    s = s.replace("\u200c", " ")  # ZWNJ
    # unify half/quarter glyphs and spaces
    s = s.replace("½", "half ").replace("¼", "quarter ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------
# Data model (loose on purpose)
# ---------------------------

@dataclass
class Payload:
    fetchedAtMs: int
    source: str
    rates: Dict[str, Dict[str, Any]]


def load_template(path: str) -> Payload:
    """
    Load the current JSON file as a template so we preserve:
      - emoji/fa/title/kind/unit
      - future fields (aliases/inputMode/lists/schemaVersion/...)
    """
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)

    if not isinstance(obj, dict) or "rates" not in obj or not isinstance(obj["rates"], dict):
        raise RuntimeError(f"Template JSON is invalid: {path}")

    fetched = int(obj.get("fetchedAtMs") or 0)
    source = str(obj.get("source") or "")
    rates = obj["rates"]

    return Payload(fetchedAtMs=fetched, source=source, rates=rates)


# ---------------------------
# Bonbast fetch + parse
# ---------------------------

def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_bonbast_html(html: str) -> Dict[str, int]:
    """
    Returns mapping: bonbast_display_name -> integer_price
    (we'll map names to template keys later)
    """
    soup = BeautifulSoup(html, "html.parser")

    out: Dict[str, int] = {}

    # Top items by id (same as your current script)
    top_items = {
        "gol18": "Gold Gram 18k",
        "mithqal": "Gold Mithqal",
        "ounce": "Gold Ounce",
        # "ju18": "Gold Gram 18k Jewelry",  # not in template by default; handled via title matching if you add it
    }
    for elem_id, display_name in top_items.items():
        el = soup.find(id=elem_id)
        if not el:
            continue
        p = to_int_price(el.get_text(strip=True))
        if p is not None:
            out[display_name] = p

    # Tables (same heuristic as your current script)
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            name = ""
            price = ""

            if len(cols) == 4:
                name = cols[1].get_text(strip=True)
                price = cols[2].get_text(strip=True)
            elif len(cols) == 3:
                name = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)

            p = to_int_price(price)
            if not name or p is None:
                continue

            # Normalize coin naming (copied from your current logic)
            if "Emami" in name:
                name = "Emami"
            elif "Azadi" in name and "Gera" not in name and "½" not in name and "¼" not in name:
                name = "Azadi"
            elif "Half" in name:
                name = "½ Azadi"
            elif "Quarter" in name:
                name = "¼ Azadi"
            elif "Gram" in name and "Coin" in name:
                name = "Gerami"

            out[name] = p

    return out


def scrape_bonbast_fast() -> Dict[str, int]:
    """Fast path: plain HTTP fetch."""
    html = http_get(BONBAST_URL, timeout=20)
    parsed = parse_bonbast_html(html)
    return parsed


def scrape_bonbast_selenium() -> Dict[str, int]:
    """Slow fallback: Selenium (kept optional)."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
    except Exception as e:
        raise RuntimeError(f"Selenium fallback requested but deps missing: {e}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(BONBAST_URL)

        # cheaper than sleep(15): wait for at least one table to exist
        WebDriverWait(driver, SELENIUM_WAIT_SECONDS).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )

        html = driver.page_source
        parsed = parse_bonbast_html(html)
        return parsed
    finally:
        if driver:
            driver.quit()


def scrape_bonbast() -> Dict[str, int]:
    # Try HTTP first (fast/cheap)
    try:
        data = scrape_bonbast_fast()
        # heuristic: if very few items, page probably needs JS or blocked
        if len(data) >= 15:
            return data
        print(f"[bonbast] HTTP parse returned only {len(data)} items -> trying Selenium fallback...")
    except Exception as e:
        print(f"[bonbast] HTTP fetch failed: {e} -> trying Selenium fallback...")

    if not USE_SELENIUM_FALLBACK:
        return {}

    try:
        data = scrape_bonbast_selenium()
        return data
    except Exception as e:
        print(f"[bonbast] Selenium failed: {e}")
        return {}


# ---------------------------
# Crypto CSV fetch
# ---------------------------

def fetch_crypto_csv(url: str) -> Dict[str, Tuple[float, float]]:
    """
    Returns: name -> (usd_price, change24h_fraction)
    where change24h_fraction is like 0.054 (== 5.4%)
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*;q=0.8"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return {}

    required = {"name", "price", "percent_change_24h"}
    if not required.issubset(set(reader.fieldnames)):
        print(f"[crypto] CSV missing required columns. Found: {reader.fieldnames}")
        return {}

    out: Dict[str, Tuple[float, float]] = {}
    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        try:
            usd_price = float(row.get("price") or 0.0)
            pct = float(row.get("percent_change_24h") or 0.0)
        except Exception:
            continue
        out[name] = (usd_price, pct / 100.0)
    return out


# ---------------------------
# Update template in-place
# ---------------------------

COIN_NAME_TO_KEY = {
    "Emami": "coin_emami",
    "Azadi": "coin_azadi",
    "½ Azadi": "coin_half_azadi",
    "¼ Azadi": "coin_quarter_azadi",
    "Gerami": "coin_gerami",
}

TOP_NAME_TO_KEY = {
    "Gold Gram 18k": "gold_gram_18k",
    "Gold Mithqal": "gold_mithqal",
    "Gold Ounce": "gold_ounce",
}


def build_title_index(rates: Dict[str, Dict[str, Any]], kind: str) -> Dict[str, str]:
    """title normalized -> key"""
    idx: Dict[str, str] = {}
    for key, r in rates.items():
        if str(r.get("kind")) != kind:
            continue
        title = str(r.get("title") or "")
        if title:
            idx[norm_key(title)] = key
    return idx


def update_from_bonbast(payload: Payload, bonbast: Dict[str, int]) -> None:
    rates = payload.rates

    currency_title_idx = build_title_index(rates, "currency")
    # also allow matching by existing fa (in case bonbast changes to Persian later)
    currency_fa_idx = {norm_key(str(v.get("fa") or "")): k for k, v in rates.items() if v.get("kind") == "currency" and v.get("fa")}

    updated = 0
    skipped = 0

    for name, price in bonbast.items():
        key = COIN_NAME_TO_KEY.get(name) or TOP_NAME_TO_KEY.get(name)

        if not key:
            nk = norm_key(name)
            key = currency_title_idx.get(nk) or currency_fa_idx.get(nk)

        if not key or key not in rates:
            skipped += 1
            continue

        rates[key]["price"] = price
        updated += 1

    print(f"[bonbast] updated={updated} skipped={skipped}")


def recompute_usd_relations(payload: Payload) -> None:
    rates = payload.rates
    usd = rates.get("usd")
    usd_price = None
    if usd and isinstance(usd.get("price"), (int, float)) and usd["price"]:
        usd_price = float(usd["price"])

    if not usd_price:
        print("[usdPrice] usd price missing; skipping usdPrice recompute")
        return

    for key, r in rates.items():
        kind = str(r.get("kind") or "")
        if kind not in ("currency", "crypto"):
            continue

        # keep existing fields and only update if present or if it makes sense
        if kind == "currency":
            if key == "usd":
                r["usdPrice"] = 1
            else:
                if "usdPrice" in r:
                    r["usdPrice"] = float(r.get("price", 0.0)) / usd_price

        elif kind == "crypto":
            # for crypto we always want local price = usdPrice * usd_local
            if "usdPrice" in r and isinstance(r["usdPrice"], (int, float)):
                r["price"] = float(r["usdPrice"]) * usd_price

    # Special case: gold_ounce has usdPrice and is used like crypto (in your current JSON sample)
    go = rates.get("gold_ounce")
    if go and isinstance(go.get("price"), (int, float)) and usd_price and "usdPrice" in go:
        go["usdPrice"] = float(go["price"]) / usd_price


def update_from_crypto_csv(payload: Payload, crypto: Dict[str, Tuple[float, float]]) -> None:
    rates = payload.rates
    usd = rates.get("usd")
    usd_local = float(usd.get("price")) if usd and usd.get("price") else None
    if not usd_local:
        print("[crypto] usd local price missing; cannot compute local crypto price")
        usd_local = 1.0

    crypto_title_idx = build_title_index(rates, "crypto")

    updated = 0
    skipped = 0

    for name, (usd_price, change24h) in crypto.items():
        key = crypto_title_idx.get(norm_key(name))
        if not key:
            skipped += 1
            continue

        r = rates.get(key)
        if not r:
            skipped += 1
            continue

        r["usdPrice"] = float(usd_price)
        r["change24h"] = float(change24h)
        r["price"] = float(usd_price) * float(usd_local)
        updated += 1

    print(f"[crypto] updated={updated} skipped={skipped}")


# ---------------------------
# Validation (before writing)
# ---------------------------

_ALLOWED_KINDS = {"currency", "crypto", "gold"}


def validate_payload(payload: Payload) -> Tuple[bool, str]:
    if not payload.rates or not isinstance(payload.rates, dict):
        return False, "rates missing/invalid"

    if len(payload.rates) < 80:
        return False, f"rates too small: {len(payload.rates)}"

    for k, r in payload.rates.items():
        if not isinstance(r, dict):
            return False, f"rate {k} not an object"
        kind = str(r.get("kind") or "")
        if kind and kind not in _ALLOWED_KINDS:
            return False, f"rate {k} invalid kind: {kind}"
        unit = r.get("unit", 1)
        if not isinstance(unit, int) or unit < 1:
            return False, f"rate {k} invalid unit: {unit}"
        price = r.get("price")
        if price is None or not isinstance(price, (int, float)):
            return False, f"rate {k} invalid price: {price}"

    return True, "ok"


# ---------------------------
# Main
# ---------------------------

def main() -> int:
    if not os.path.exists(TEMPLATE_FILE):
        print(f"Template file not found: {TEMPLATE_FILE}")
        print("Tip: commit a baseline rates_v2_latest first (with metadata/aliases/etc).")
        return 2

    payload = load_template(TEMPLATE_FILE)

    bonbast = scrape_bonbast()
    if bonbast:
        update_from_bonbast(payload, bonbast)
    else:
        print("[bonbast] no data collected; will keep previous prices")

    crypto = {}
    try:
        crypto = fetch_crypto_csv(CRYPTO_CSV_URL)
    except Exception as e:
        print(f"[crypto] fetch failed: {e}")

    if crypto:
        update_from_crypto_csv(payload, crypto)
    else:
        print("[crypto] no data collected; will keep previous crypto values")

    # recompute usdPrice relations & local crypto prices
    recompute_usd_relations(payload)

    # update fetchedAtMs + source
    payload.fetchedAtMs = int(time.time() * 1000)
    payload.source = f"{BONBAST_URL} + {CRYPTO_CSV_URL}"

    ok, msg = validate_payload(payload)
    if not ok:
        print(f"[validate] FAILED: {msg}")
        return 3

    # Write output (minified) preserving insertion order from template dict
    out_obj: Dict[str, Any] = {
        "fetchedAtMs": payload.fetchedAtMs,
        "source": payload.source,
        "rates": payload.rates,
    }

    # Preserve any extra top-level keys you might add later (schemaVersion, lists, etc.)
    # Load template again and merge unknown keys
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        original = json.load(f)
    for k, v in original.items():
        if k not in out_obj:
            out_obj[k] = v

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, separators=(",", ":"))

    print(f"✅ wrote {OUTPUT_FILE} with {len(payload.rates)} rates; fetchedAtMs={payload.fetchedAtMs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
