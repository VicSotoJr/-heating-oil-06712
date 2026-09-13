import json, re
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ZIP = "06712"
OUT = Path("data/prices.json")
HEADERS = {"User-Agent": "06712-heating-oil-dashboard/1.0"}

SOURCES = [
    ("First Fuel Oil", "https://www.firstfueloil.com/"),
    ("Phillips Oil & Propane", "https://phillipsoilllc.com/"),
    ("Curtiss Oil", "https://curtissoil.com/get-price/"),
    ("Incredible Oil & Propane", "https://www.incredibleoil.com/"),
]

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text

def money(s):
    m = re.search(r'\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)', s.replace(",", ""))
    return float(m.group(1)) if m else None

def text(html):
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

def first_fuel(html):
    t = text(html)
    # Prefer the explicitly labelled 100-299 tier.
    m = re.search(r'100\\s*[-–]\\s*299\\s*Gallons\\s*\\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)', t, re.I)
    return float(m.group(1)) if m else None

def phillips(html):
    t = text(html)
    m = re.search(r'Heating Oil Prices.*?\\b100\\b\\s+\\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)', t, re.I)
    if m: return float(m.group(1))
    # fallback: a visible row such as "100 $5.290 $529.00"
    m = re.search(r'\\b100\\s+\\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)\\s+\\$\\s*[0-9]', t)
    return float(m.group(1)) if m else None

def incredible(html):
    t = text(html)
    m = re.search(r'100\\s*[-–]\\s*299\\s*Gallons\\s*\\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)', t, re.I)
    return float(m.group(1)) if m else None

def curtiss(html):
    # Curtiss currently uses an online quote flow. This parser accepts a visible
    # 100-gallon quote if the site exposes it in server-rendered HTML.
    t = text(html)
    patterns = [
        r'\\b100\\s+Gallons?\\s*\\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)',
        r'100\\s*[-–]\\s*199\\s*Gallons?\\s*\\$\\s*([0-9]+(?:\\.[0-9]{1,3})?)',
    ]
    for p in patterns:
        m = re.search(p, t, re.I)
        if m: return float(m.group(1))
    return None

PARSERS = {
    "First Fuel Oil": first_fuel,
    "Phillips Oil & Propane": phillips,
    "Curtiss Oil": curtiss,
    "Incredible Oil & Propane": incredible,
}

def main():
    result = {"zip": ZIP, "gallons": 100, "updated_at": datetime.now(timezone.utc).isoformat(), "sources": []}
    for name, url in SOURCES:
        item = {"name": name, "url": url, "price_per_gallon": None, "note": "Could not extract a public 100-gallon quote."}
        try:
            html = get(url)
            p = PARSERS[name](html)
            if p is not None:
                item["price_per_gallon"] = round(p, 3)
                item["note"] = "100-gallon tier/quote"
        except Exception as e:
            item["note"] = "Source unavailable during update."
        result["sources"].append(item)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
