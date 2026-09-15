import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# =========================================================
# CONFIG
# =========================================================

ZIP = "06712"
GALLONS = 100
OUT = Path("data/prices.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HeatingOil06712/1.0)"
}


# =========================================================
# BASIC HELPERS
# =========================================================

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


def extract_prices(text):
    """
    Return all dollar prices found in text.

    Example:
        $3.499
        $3.49
        $5.25
    """
    if not text:
        return []

    matches = re.findall(
        r"\$\s*(\d+\.\d{2,3})",
        text
    )

    return [
        float(value)
        for value in matches
    ]


# =========================================================
# 100-149 GALLON PRICE EXTRACTION
# =========================================================

def extract_100_149_price(text):
    """
    Look for a price associated with a 100-149 gallon tier.
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

        # 100-149 without the word gallons
        r"100\s*[-–—]\s*149.{0,200}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:
            return float(match.group(1))

    return None


# =========================================================
# 100+ GALLON PRICE EXTRACTION
# =========================================================

def extract_100_plus_price(text):
    """
    Look for a price associated with a 100+ gallon tier.
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

        # 100 gallons or more
        r"100\s+gallons?.{0,100}?(?:or|and)\s+more.{0,300}?\$\s*(\d+\.\d{2,3})",

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
            return float(match.group(1))

    return None


# =========================================================
# 100-GALLON PUBLISHED PRICE
# =========================================================

def extract_published_100_price(text):
    """
    Handles common published pricing such as:

        100-299 Gallons $3.499
        100-299 gallons: $3.49
        100 Gallons $3.49
    """

    text = clean_text(text)

    patterns = [

        r"100\s*[-–—]\s*299\s*Gallons?.{0,200}?\$\s*(\d+\.\d{2,3})",

        r"100\s*[-–—]\s*299.{0,200}?\$\s*(\d+\.\d{2,3})",

        r"100\s*[-–—]\s*299.{0,200}?(\d+\.\d{2,3})\s*(?:per|/)?\s*gallon",

        r"100\s+Gallons?.{0,150}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:
            return float(match.group(1))

    return None


# =========================================================
# GENERIC PRICE FINDER
# =========================================================

def find_price_in_text(text):

    # Best match first:
    # 100-149
    price = extract_100_149_price(text)

    if price is not None:
        return (
            price,
            "ZIP-specific 100-149 gallon price"
        )

    # Then 100+
    price = extract_100_plus_price(text)

    if price is not None:
        return (
            price,
            "ZIP-specific 100+ gallon price"
        )

    # Then common published 100-299 pricing
    price = extract_published_100_price(text)

    if price is not None:
        return (
            price,
            "Published 100-gallon price"
        )

    return None


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
        soup.get_text(
            " ",
            strip=True
        )
    )

    price = extract_published_100_price(text)

    if price is not None:
        return (
            price,
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

    # Check tables first because Phillips publishes
    # pricing in a table.

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

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    price = find_price_in_text(text)

    if price:
        return price

    raise RuntimeError(
        "Could not find Phillips 100-gallon price"
    )


# =========================================================
# CURTISS OIL
# =========================================================

def curtiss():

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
# GENERIC PLAYWRIGHT QUOTE PAGE
# =========================================================

def quote_page_100_plus(
    url,
    supplier_name
):

    """
    Generic ZIP-specific quote scraper.

    Tries:
      1. Supplied URL
      2. /get-price/
      3. /get-price
      4. Homepage

    Then attempts:
      - ZIP input
      - Check Price button
      - Submit button
      - Price button
      - page text
      - HTML
      - network/API responses
    """

    candidate_urls = []

    # Supplied URL first
    candidate_urls.append(url)

    # Add get-price variants
    base = url.rstrip("/")

    if "/get-price" not in base.lower():

        candidate_urls.append(
            base + "/get-price/"
        )

        candidate_urls.append(
            base + "/get-price"
        )

    # Remove duplicates
    candidate_urls = list(
        dict.fromkeys(candidate_urls)
    )

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
                    "api",
                    "ajax"
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

        diagnostic_text = []

        try:

            for candidate_url in candidate_urls:

                try:

                    page.goto(
                        candidate_url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.wait_for_timeout(
                        5000
                    )

                    # -------------------------------------------------
                    # LOOK FOR ZIP
                    # -------------------------------------------------

                    zip_selectors = [
                        'input[name*="zip" i]',
                        'input[id*="zip" i]',
                        'input[placeholder*="zip" i]',
                        'input[aria-label*="zip" i]',
                        'input[name*="postal" i]',
                        'input[id*="postal" i]',
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

                    # -------------------------------------------------
                    # IF ZIP EXISTS, ENTER IT
                    # -------------------------------------------------

                    if zip_box is not None:

                        try:

                            zip_box.fill(
                                ZIP
                            )

                        except Exception:

                            continue

                        # -------------------------------------------------
                        # FIND SUBMIT BUTTON
                        # -------------------------------------------------

                        check_selectors = [

                            'button:has-text("Check Price")',

                            'button:has-text("Check price")',

                            'button:has-text("Get Price")',

                            'button:has-text("Get price")',

                            'button:has-text("View Price")',

                            'button:has-text("View price")',

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

                                    check_button = (
                                        locator.first
                                    )

                                    break

                            except Exception:
                                continue

                        if check_button is not None:

                            try:

                                check_button.click()

                                page.wait_for_timeout(
                                    10000
                                )

                            except Exception:
                                pass

                    # -------------------------------------------------
                    # SEARCH PAGE + FRAMES
                    # -------------------------------------------------

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

                            price = find_price_in_text(
                                body
                            )

                            if price is not None:

                                browser.close()

                                return price

                        except Exception:
                            continue

                    # -------------------------------------------------
                    # SEARCH HTML
                    # -------------------------------------------------

                    for frame in page.frames:

                        try:

                            html = frame.content()

                            html_text = clean_text(
                                html
                            )

                            price = find_price_in_text(
                                html_text
                            )

                            if price is not None:

                                browser.close()

                                return price

                        except Exception:
                            continue

                except Exception as error:

                    diagnostic_text.append(
                        f"{candidate_url} failed: "
                        f"{type(error).__name__}: "
                        f"{str(error)[:250]}"
                    )

                    continue

            # ---------------------------------------------------------
            # NETWORK/API FALLBACK
            # ---------------------------------------------------------

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

                        price = find_price_in_text(
                            response_text
                        )

                        if price is not None:

                            browser.close()

                            return price

                except Exception:
                    continue

            # ---------------------------------------------------------
            # DIAGNOSTICS
            # ---------------------------------------------------------

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

            browser.close()

            return (
                None,
                "ZIP accepted or page loaded, but 100+ gallon price was not found."
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

    price = extract_published_100_price(
        text
    )

    if price is not None:

        return (
            price,
            "Published 100-299 gallon price"
        )

    raise RuntimeError(
        "Could not find Incredible Oil 100-gallon price"
    )


# =========================================================
# BETHANY FUEL
# =========================================================

def bethany_fuel():

    return quote_page_100_plus(
        "https://www.bethanyfuel.com/",
        "Bethany Fuel"
    )


# =========================================================
# FJ BOIL
# =========================================================

def fj_boil():

    return quote_page_100_plus(
        "https://www.fjboil.com/",
        "FJ Boil"
    )


# =========================================================
# EASY OIL CT
# =========================================================

def easy_oil_ct():

    return quote_page_100_plus(
        "https://www.easyoilct.com/",
        "Easy Oil CT"
    )


# =========================================================
# GG OIL CT
# =========================================================

def gg_oil_ct():

    return quote_page_100_plus(
        "https://www.ggoilct.com/",
        "GG Oil CT"
    )


# =========================================================
# NEW SUPPLIERS
# =========================================================


# ---------------------------------------------------------
# BELICA FUEL
# ---------------------------------------------------------

def belica_fuel():

    return quote_page_100_plus(
        "https://belicafuel.com/",
        "Belica Fuel"
    )


# ---------------------------------------------------------
# BLUE FLAME OIL
# ---------------------------------------------------------

def blue_flame_oil():

    return quote_page_100_plus(
        "https://blueflameoil.com/",
        "Blue Flame Oil"
    )


# ---------------------------------------------------------
# DIME OIL
# ---------------------------------------------------------

def dime_oil():

    return quote_page_100_plus(
        "https://dimeoil.com/",
        "Dime Oil"
    )


# ---------------------------------------------------------
# FEDERAL OIL
# ---------------------------------------------------------

def federal_oil():

    return quote_page_100_plus(
        "https://federaloil.com/",
        "Federal Oil"
    )


# ---------------------------------------------------------
# IT ENERGY
# ---------------------------------------------------------

def it_energy():

    return quote_page_100_plus(
        "https://itenergyct.com/",
        "IT Energy"
    )


# ---------------------------------------------------------
# PURPLE FUELS
# ---------------------------------------------------------

def purple_fuels():

    return quote_page_100_plus(
        "https://purplefuels.com/",
        "Purple Fuels"
    )


# ---------------------------------------------------------
# OMNI ENERGY
# ---------------------------------------------------------

def omni_energy():

    return quote_page_100_plus(
        "https://omnienergy.net/",
        "Omni Energy"
    )


# ---------------------------------------------------------
# BARIBAULT FUEL
# ---------------------------------------------------------

def baribault_fuel():

    return quote_page_100_plus(
        "https://baribaultfuel.com/",
        "Baribault Fuel"
    )


# ---------------------------------------------------------
# BRAZOS OIL
# ---------------------------------------------------------

def brazos_oil():

    return quote_page_100_plus(
        "https://brazosoil.com/",
        "Brazos Oil"
    )


# ---------------------------------------------------------
# CENTSABLE OIL
# ---------------------------------------------------------

def centsable_oil():

    return quote_page_100_plus(
        "https://centsableoil.com/",
        "Centsable Oil"
    )


# ---------------------------------------------------------
# EAGLE OIL
# ---------------------------------------------------------

def eagle_oil():

    return quote_page_100_plus(
        "https://eagleoilcompany.com/",
        "Eagle Oil Company"
    )


# ---------------------------------------------------------
# OIL GUY
# ---------------------------------------------------------

def oil_guy():

    return quote_page_100_plus(
        "https://oilguyllc.com/",
        "Oil Guy LLC"
    )


# ---------------------------------------------------------
# PREMIER ENERGY
# ---------------------------------------------------------

def premier_energy():

    return quote_page_100_plus(
        "https://premierenergyct.com/",
        "Premier Energy"
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

        "total_for_100_gallons": None,

        "note": "Unavailable"

    }

    try:

        price, note = function()

        if price is not None:

            result["price_per_gallon"] = round(
                price,
                3
            )

            result["total_for_100_gallons"] = round(
                price * GALLONS,
                2
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

        # =====================================================
        # EXISTING 10
        # =====================================================

        run_supplier(
            "First Fuel Oil",
            "https://www.firstfueloil.com/",
            first_fuel
        ),

        run_supplier(
            "Phillips Oil & Propane",
            "https://phillipsoilllc.com/",
            phillips
        ),

        run_supplier(
            "Curtiss Oil",
            "https://curtissoil.com/get-price/",
            curtiss
        ),

        run_supplier(
            "Incredible Oil & Propane",
            "https://www.incredibleoil.com/home-heating-oil/",
            incredible_oil
        ),

        run_supplier(
            "Anytime Oil",
            "https://anytime-oil.com/get-price/",
            anytime_oil
        ),

        run_supplier(
            "Right Energy",
            "https://www.rightenergyct.com/get-price/",
            right_energy
        ),

        run_supplier(
            "Bethany Fuel",
            "https://www.bethanyfuel.com/",
            bethany_fuel
        ),

        run_supplier(
            "FJ Boil",
            "https://www.fjboil.com/",
            fj_boil
        ),

        run_supplier(
            "Easy Oil CT",
            "https://www.easyoilct.com/",
            easy_oil_ct
        ),

        run_supplier(
            "GG Oil CT",
            "https://www.ggoilct.com/",
            gg_oil_ct
        ),


        # =====================================================
        # ADDITIONAL PROSPECT SUPPLIERS
        # =====================================================

        run_supplier(
            "Belica Fuel",
            "https://belicafuel.com/",
            belica_fuel
        ),

        run_supplier(
            "Blue Flame Oil",
            "https://blueflameoil.com/",
            blue_flame_oil
        ),

        run_supplier(
            "Dime Oil",
            "https://dimeoil.com/",
            dime_oil
        ),

        run_supplier(
            "Federal Oil",
            "https://federaloil.com/",
            federal_oil
        ),

        run_supplier(
            "IT Energy",
            "https://itenergyct.com/",
            it_energy
        ),

        run_supplier(
            "Purple Fuels",
            "https://purplefuels.com/",
            purple_fuels
        ),

        run_supplier(
            "Omni Energy",
            "https://omnienergy.net/",
            omni_energy
        ),

        run_supplier(
            "Baribault Fuel",
            "https://baribaultfuel.com/",
            baribault_fuel
        ),

        run_supplier(
            "Brazos Oil",
            "https://brazosoil.com/",
            brazos_oil
        ),

        run_supplier(
            "Centsable Oil",
            "https://centsableoil.com/",
            centsable_oil
        ),

        run_supplier(
            "Eagle Oil Company",
            "https://eagleoilcompany.com/",
            eagle_oil
        ),

        run_supplier(
            "Oil Guy LLC",
            "https://oilguyllc.com/",
            oil_guy
        ),

        run_supplier(
            "Premier Energy",
            "https://premierenergyct.com/",
            premier_energy
        ),
    ]


    # =========================================================
    # SORT RESULTS
    # =========================================================

    # Cheapest available prices first.
    # Suppliers without a price go to the bottom.

    suppliers.sort(
        key=lambda x: (
            x["price_per_gallon"] is None,
            x["price_per_gallon"]
            if x["price_per_gallon"] is not None
            else float("inf")
        )
    )


    # =========================================================
    # OUTPUT
    # =========================================================

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


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()