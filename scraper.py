import json
import re
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
ZIP = "06712"
GALLONS = 100
OUT = Path("data/prices.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HeatingOil06712/1.0)"
}
def get_html(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return response.text
def clean_text(value):
    return re.sub(r"\s+", " ", value).strip()
# =========================================================
# FIRST FUEL OIL
# =========================================================
def first_fuel():
    html = get_html(
        "https://www.firstfueloil.com/"
    )
    soup = BeautifulSoup(
        html,
        "html.parser"
    )
    text = clean_text(
        soup.get_text(" ", strip=True)
    )
    patterns = [
        r"100\s*[-–—]\s*299\s*Gallons?.{0,150}?\$\s*(\d+\.\d{2,3})",
        r"100\s*[-–—]\s*299.{0,150}?\$\s*(\d+\.\d{2,3})",
    ]
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I
        )
        if match:
            return (
                float(match.group(1)),
                "Published 100-299 gallon price"
            )
    raise RuntimeError(
        "Could not find First Fuel 100-gallon price"
    )
# =========================================================
# PHILLIPS OIL
# =========================================================
def phillips():
    html = get_html(
        "https://phillipsoilllc.com/"
    )
    soup = BeautifulSoup(
        html,
        "html.parser"
    )
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = [
                clean_text(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )
                for cell in row.find_all(
                    ["td", "th"]
                )
            ]
            if not cells:
                continue
            if cells[0].strip() == "100":
                for cell in cells[1:]:
                    match = re.search(
                        r"\$\s*(\d+\.\d{2,3})",
                        cell
                    )
                    if match:
                        return (
                            float(match.group(1)),
                            "Published 100-gallon price"
                        )
    raise RuntimeError(
        "Could not find Phillips 100-gallon price"
    )
# =========================================================
# GENERIC 100-149 GALLON PRICE EXTRACTION
# =========================================================
def extract_100_149_price(text):
    """
    Look for a price associated with a 100-149 gallon tier.
    Handles variations such as:
        100-149 gallons
        100 - 149 gallons
        100-149 gal
        100 to 149 gallons
    """
    text = clean_text(text)
    patterns = [
        # 100-149 gallons -> price
        r"100\s*[-–—]\s*149\s*gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
        # Price -> 100-149 gallons
        r"\$\s*(\d+\.\d{2,3}).{0,300}?100\s*[-–—]\s*149\s*gallons?",
        # 100-149 gal -> price
        r"100\s*[-–—]\s*149\s*gal(?:lon)?s?.{0,300}?\$\s*(\d+\.\d{2,3})",
        # 100 to 149 gallons
        r"100\s+(?:to|through)\s+149\s+gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
    ]
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I
        )
        if match:
            return float(
                match.group(1)
            )
    return None
# =========================================================
# GENERIC 100+ GALLON PRICE EXTRACTION
# =========================================================
def extract_100_plus_price(text):
    """
    Look for a price associated with a 100+ gallon tier.
    Handles variations such as:
        100+ gallons
        100 + gallons
        100+ gallon
        100 + gallon
        100+ gal
        100 gallons and more
    """
    text = clean_text(text)
    patterns = [
        # 100+ gallons -> price
        r"100\s*\+\s*gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
        # Price -> 100+ gallons
        r"\$\s*(\d+\.\d{2,3}).{0,300}?100\s*\+\s*gallons?",
        # 100+ gal -> price
        r"100\s*\+\s*gal(?:lon)?s?.{0,300}?\$\s*(\d+\.\d{2,3})",
        # 100 gallons and more
        r"100\s+gallons?\s+(?:and|or)\s+(?:more|over).{0,300}?\$\s*(\d+\.\d{2,3})",
        # General fallback
        r"100\s*\+.{0,200}?\$\s*(\d+\.\d{2,3})",
    ]
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I
        )
        if match:
            return float(
                match.group(1)
            )
    return None
# =========================================================
# GENERIC PLAYWRIGHT QUOTE PAGE
# =========================================================
def quote_page_100_plus(
    url,
    supplier_name
):
    """
    Enter ZIP code into a supplier's online quote page
    and find pricing (tries 100-149 first, then 100+).
    This does NOT proceed into tank settings,
    checkout, payment, or ordering.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200
            }
        )
        network_responses = []
        def handle_response(response):
            try:
                response_url = (
                    response.url.lower()
                )
                interesting_terms = [
                    "price",
                    "quote",
                    "fuel",
                    "product",
                    "order",
                    "api"
                ]
                if any(
                    term in response_url
                    for term in interesting_terms
                ):
                    network_responses.append(
                        response
                    )
            except Exception:
                pass
        page.on(
            "response",
            handle_response
        )
        try:
            # -------------------------------------------------
            # LOAD PAGE
            # -------------------------------------------------
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )
            page.wait_for_timeout(
                5000
            )
            # -------------------------------------------------
            # FIND ZIP INPUT
            # -------------------------------------------------
            zip_selectors = [
                'input[name*="zip" i]',
                'input[id*="zip" i]',
                'input[placeholder*="zip" i]',
                'input[aria-label*="zip" i]',
            ]
            zip_box = None
            for selector in zip_selectors:
                try:
                    locator = page.locator(
                        selector
                    )
                    if locator.count() > 0:
                        zip_box = locator.first
                        break
                except Exception:
                    continue
            if zip_box is None:
                raise RuntimeError(
                    f"{supplier_name} ZIP input not found"
                )
            # -------------------------------------------------
            # ENTER ZIP
            # -------------------------------------------------
            zip_box.fill(
                ZIP
            )
            # -------------------------------------------------
            # FIND CHECK PRICE BUTTON
            # -------------------------------------------------
            check_selectors = [
                'button:has-text("Check Price")',
                'button:has-text("Check price")',
                'button:has-text("Check")',
                'input[type="submit"]',
                'button:has-text("Price")',
            ]
            check_button = None
            for selector in check_selectors:
                try:
                    locator = page.locator(
                        selector
                    )
                    if locator.count() > 0:
                        check_button = locator.first
                        break
                except Exception:
                    continue
            if check_button is None:
                raise RuntimeError(
                    f"{supplier_name} Check Price button not found"
                )
            # -------------------------------------------------
            # SUBMIT ZIP
            # -------------------------------------------------
            check_button.click()
            page.wait_for_timeout(
                10000
            )
            # -------------------------------------------------
            # SEARCH MAIN PAGE + FRAMES
            # -------------------------------------------------
            diagnostic_text = []
            for frame in page.frames:
                try:
                    body = frame.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    )
                    body = clean_text(
                        body
                    )
                    if body:
                        diagnostic_text.append(
                            body
                        )
                    # Try 100-149 first
                    price = extract_100_149_price(
                        body
                    )
                    if price is not None:
                        browser.close()
                        return (
                            price,
                            "ZIP-specific 100-149 gallon price"
                        )
                    # Fall back to 100+
                    price = extract_100_plus_price(
                        body
                    )
                    if price is not None:
                        browser.close()
                        return (
                            price,
                            "ZIP-specific 100+ gallon price"
                        )
                except Exception:
                    continue
            # -------------------------------------------------
            # SEARCH PAGE HTML
            # -------------------------------------------------
            for frame in page.frames:
                try:
                    html = frame.content()
                    html_text = clean_text(
                        html
                    )
                    # Try 100-149 first
                    price = extract_100_149_price(
                        html_text
                    )
                    if price is not None:
                        browser.close()
                        return (
                            price,
                            "ZIP-specific 100-149 gallon price"
                        )
                    # Fall back to 100+
                    price = extract_100_plus_price(
                        html_text
                    )
                    if price is not None:
                        browser.close()
                        return (
                            price,
                            "ZIP-specific 100+ gallon price"
                        )
                except Exception:
                    continue
            # -------------------------------------------------
            # NETWORK/API FALLBACK
            # -------------------------------------------------
            for response in network_responses:
                try:
                    content_type = (
                        response.headers.get(
                            "content-type",
                            ""
                        ).lower()
                    )
                    if (
                        "json" in content_type
                        or "text" in content_type
                        or "javascript" in content_type
                        or "html" in content_type
                    ):
                        response_text = (
                            response.text()
                        )
                        # Try 100-149 first
                        price = extract_100_149_price(
                            response_text
                        )
                        if price is not None:
                            browser.close()
                            return (
                                price,
                                "ZIP-specific 100-149 gallon price"
                            )
                        # Fall back to 100+
                        price = extract_100_plus_price(
                            response_text
                        )
                        if price is not None:
                            browser.close()
                            return (
                                price,
                                "ZIP-specific 100+ gallon price"
                            )
                except Exception:
                    continue
            # -------------------------------------------------
            # DIAGNOSTIC OUTPUT
            # -------------------------------------------------
            print(
                f"\n----- {supplier_name.upper()} PAGE TEXT -----\n"
            )
            combined_text = "\n\n".join(
                diagnostic_text
            )
            print(
                combined_text[:15000]
            )
            print(
                f"\n----- END {supplier_name.upper()} PAGE TEXT -----\n"
            )
            print(
                f"\n{supplier_name}: Price was not found."
            )
            browser.close()
            return (
                None,
                "ZIP accepted, but price was not found. Check the Actions log."
            )
        except Exception as error:
            try:
                browser.close()
            except Exception:
                pass
            return (
                None,
                f"{supplier_name} quote failed: "
                + type(error).__name__
                + ": "
                + str(error)[:250]
            )
# =========================================================
# CURTISS OIL
# =========================================================
def curtiss():
    """
    Curtiss has been confirmed working with the
    100+ gallons pricing tier.
    Keep this separate so the working Curtiss
    implementation remains intact.
    """
    url = "https://curtissoil.com/get-price/"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200
            }
        )
        network_responses = []
        def handle_response(response):
            try:
                response_url = (
                    response.url.lower()
                )
                interesting_terms = [
                    "price",
                    "quote",
                    "fuel",
                    "product",
                    "order",
                    "api"
                ]
                if any(
                    term in response_url
                    for term in interesting_terms
                ):
                    network_responses.append(
                        response
                    )
            except Exception:
                pass
        page.on(
            "response",
            handle_response
        )
        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )
            page.wait_for_timeout(
                5000
            )
            # -------------------------------------------------
            # ZIP INPUT
            # -------------------------------------------------
            zip_selectors = [
                'input[name*="zip" i]',
                'input[id*="zip" i]',
                'input[placeholder*="zip" i]',
                'input[aria-label*="zip" i]',
            ]
            zip_box = None
            for selector in zip_selectors:
                try:
                    locator = page.locator(
                        selector
                    )
                    if locator.count() > 0:
                        zip_box = locator.first
                        break
                except Exception:
                    continue
            if zip_box is None:
                raise RuntimeError(
                    "Curtiss ZIP input not found"
                )
            zip_box.fill(
                ZIP
            )
            # -------------------------------------------------
            # CHECK PRICE
            # -------------------------------------------------
            check_selectors = [
                'button:has-text("Check Price")',
                'input[type="submit"]',
                'button:has-text("Check")',
                'button:has-text("Price")',
            ]
            check_button = None
            for selector in check_selectors:
                try:
                    locator = page.locator(
                        selector
                    )
                    if locator.count() > 0:
                        check_button = locator.first
                        break
                except Exception:
                    continue
            if check_button is None:
                raise RuntimeError(
                    "Curtiss Check Price button not found"
                )
            check_button.click()
            page.wait_for_timeout(
                10000
            )
            # -------------------------------------------------
            # SEARCH ALL FRAMES
            # -------------------------------------------------
            page_text = ""
            for frame in page.frames:
                try:
                    body = frame.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    )
                    body = clean_text(
                        body
                    )
                    if body:
                        page_text += "\n" + body
                    price = extract_100_plus_price(
                        body
                    )
                    if price is not None:
                        browser.close()
                        return (
                            price,
                            "ZIP-specific 100+ gallon price"
                        )
                except Exception:
                    continue
            # -------------------------------------------------
            # SEARCH HTML
            # -------------------------------------------------
            for frame in page.frames:
                try:
                    html = frame.content()
                    price = extract_100_plus_price(
                        clean_text(html)
                    )
                    if price is not None:
                        browser.close()
                        return (
                            price,
                            "ZIP-specific 100+ gallon price"
                        )
                except Exception:
                    continue
            # -------------------------------------------------
            # NETWORK FALLBACK
            # -------------------------------------------------
            for response in network_responses:
                try:
                    content_type = (
                        response.headers.get(
                            "content-type",
                            ""
                        ).lower()
                    )
                    if (
                        "json" in content_type
                        or "text" in content_type
                        or "javascript" in content_type
                        or "html" in content_type
                    ):
                        response_text = (
                            response.text()
                        )
                        price = extract_100_plus_price(
                            response_text
                        )
                        if price is not None:
                            browser.close()
                            return (
                                price,
                                "ZIP-specific 100+ gallon price"
                            )
                except Exception:
                    continue
            # -------------------------------------------------
            # DIAGNOSTICS
            # -------------------------------------------------
            print(
                "\n----- CURTISS PAGE TEXT -----\n"
            )
            print(
                page_text[:15000]
            )
            print(
                "\n----- END CURTISS PAGE TEXT -----\n"
            )
            browser.close()
            return (
                None,
                "ZIP accepted, but Curtiss 100+ gallon price was not found. Check the Actions log."
            )
        except Exception as error:
            try:
                browser.close()
            except Exception:
                pass
            return (
                None,
                "Curtiss quote failed: "
                + type(error).__name__
                + ": "
                + str(error)[:250]
            )
# =========================================================
# ANYTIME OIL
# =========================================================
def anytime_oil():
    return quote_page_100_plus(
        "https://anytime-oil.com/get-price/",
        "Anytime Oil"
    )
# =========================================================
# RIGHT ENERGY
# =========================================================
def right_energy():
    return quote_page_100_plus(
        "https://www.rightenergyct.com/get-price/",
        "Right Energy"
    )
# =========================================================
# INCREDIBLE OIL
# =========================================================
def incredible_oil():
    html = get_html(
        "https://www.incredibleoil.com/home-heating-oil/"
    )
    soup = BeautifulSoup(
        html,
        "html.parser"
    )
    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )
    patterns = [
        r"100\s*[-–—]\s*299\s*Gallons?.{0,150}?\$\s*(\d+\.\d{2,3})",
        r"100\s*[-–—]\s*299.{0,150}?\$\s*(\d+\.\d{2,3})",
    ]
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I
        )
        if match:
            return (
                float(match.group(1)),
                "Published 100-299 gallon price"
            )
    raise RuntimeError(
        "Could not find Incredible Oil 100-gallon price"
    )
# =========================================================
# SUPPLIER RUNNER
# =========================================================
def run_supplier(
    name,
    url,
    function
):
    result = {
        "name": name,
        "url": url,
        "price_per_gallon": None,
        "note": "Unavailable"
    }
    try:
        price, note = function()
        # Prevent round(None, 3) errors.
        if price is not None:
            result["price_per_gallon"] = round(
                price,
                3
            )
        result["note"] = note
    except Exception as error:
        result["note"] = (
            "Update failed: "
            + type(error).__name__
            + ": "
            + str(error)[:250]
        )
    return result
# =========================================================
# MAIN
# =========================================================
def main():
    suppliers = [
        # 1
        run_supplier(
            "First Fuel Oil",
            "https://www.firstfueloil.com/",
            first_fuel
        ),
        # 2
        run_supplier(
            "Phillips Oil & Propane",
            "https://phillipsoilllc.com/",
            phillips
        ),
        # 3
        run_supplier(
            "Curtiss Oil",
            "https://curtissoil.com/get-price/",
            curtiss
        ),
        # 4
        run_supplier(
            "Incredible Oil & Propane",
            "https://www.incredibleoil.com/home-heating-oil/",
            incredible_oil
        ),
        # 5
        run_supplier(
            "Anytime Oil",
            "https://anytime-oil.com/get-price/",
            anytime_oil
        ),
        # 6
        run_supplier(
            "Right Energy",
            "https://www.rightenergyct.com/get-price/",
            right_energy
        ),
    ]
    output = {
        "zip": ZIP,
        "gallons": GALLONS,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "sources": suppliers
    }
    OUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    OUT.write_text(
        json.dumps(
            output,
            indent=2
        ),
        encoding="utf-8"
    )
    print(
        json.dumps(
            output,
            indent=2
        )
    )
if __name__ == "__main__":
    main()
