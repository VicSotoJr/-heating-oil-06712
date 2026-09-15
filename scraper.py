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


def soup_text(url):
    html = get_html(url)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    return clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )


# =========================================================
# PRICE EXTRACTION HELPERS
# =========================================================

def extract_100_149_price(text):
    text = clean_text(text)

    patterns = [
        r"100\s*[-–—]\s*149\s*gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
        r"\$\s*(\d+\.\d{2,3}).{0,300}?100\s*[-–—]\s*149\s*gallons?",
        r"100\s*[-–—]\s*149\s*gal(?:lon)?s?.{0,300}?\$\s*(\d+\.\d{2,3})",
        r"100\s+(?:to|through)\s+149\s+gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return float(match.group(1))

    return None


def extract_100_299_price(text):
    text = clean_text(text)

    patterns = [
        r"100\s*[-–—]\s*299\s*gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
        r"\$\s*(\d+\.\d{2,3}).{0,300}?100\s*[-–—]\s*299\s*gallons?",
        r"100\s*[-–—]\s*299\s*gal(?:lon)?s?.{0,300}?\$\s*(\d+\.\d{2,3})",
        r"100\s*[-–—]\s*299.{0,300}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return float(match.group(1))

    return None


def extract_100_plus_price(text):
    text = clean_text(text)

    patterns = [
        r"100\s*\+\s*gallons?.{0,300}?\$\s*(\d+\.\d{2,3})",
        r"\$\s*(\d+\.\d{2,3}).{0,300}?100\s*\+\s*gallons?",
        r"100\s*\+\s*gal(?:lon)?s?.{0,300}?\$\s*(\d+\.\d{2,3})",
        r"100\s+gallons?\s+(?:and|or)\s+(?:more|over).{0,300}?\$\s*(\d+\.\d{2,3})",
        r"100\s+gallons?.{0,100}?(?:or|and)\s+more.{0,300}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return float(match.group(1))

    return None


def extract_100_gallon_price(text):
    text = clean_text(text)

    patterns = [
        r"100\s*gallons?.{0,200}?\$\s*(\d+\.\d{2,3})",
        r"\$\s*(\d+\.\d{2,3}).{0,200}?100\s*gallons?",
        r"minimum\s+of\s+100\s*gallons?.{0,200}?\$\s*(\d+\.\d{2,3})",
        r"minimum\s+100\s*gallons?.{0,200}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return float(match.group(1))

    return None


# =========================================================
# FIRST FUEL OIL
# =========================================================

def first_fuel():

    text = soup_text(
        "https://www.firstfueloil.com/"
    )

    price = extract_100_299_price(text)

    if price is not None:
        return (
            price,
            "Published 100-299 gallon price"
        )

    price = extract_100_149_price(text)

    if price is not None:
        return (
            price,
            "Published 100-149 gallon price"
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

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    price = extract_100_299_price(text)

    if price is not None:

        return (
            price,
            "Published 100-299 gallon price"
        )

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

                response_url = response.url.lower()

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

            page.wait_for_timeout(5000)

            zip_selectors = [
                'input[name*="zip" i]',
                'input[id*="zip" i]',
                'input[placeholder*="zip" i]',
                'input[aria-label*="zip" i]',
            ]

            zip_box = None

            for selector in zip_selectors:

                try:

                    locator = page.locator(selector)

                    if locator.count() > 0:

                        zip_box = locator.first
                        break

                except Exception:
                    continue

            if zip_box is None:

                raise RuntimeError(
                    "Curtiss ZIP input not found"
                )

            zip_box.fill(ZIP)

            check_selectors = [
                'button:has-text("Check Price")',
                'input[type="submit"]',
                'button:has-text("Check")',
                'button:has-text("Price")',
            ]

            check_button = None

            for selector in check_selectors:

                try:

                    locator = page.locator(selector)

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

            page.wait_for_timeout(10000)

            page_text = ""

            for frame in page.frames:

                try:

                    body = frame.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    )

                    body = clean_text(body)

                    if body:
                        page_text += "\n" + body

                    price = extract_100_plus_price(body)

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100+ gallon price"
                        )

                except Exception:
                    continue

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

                        response_text = response.text()

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

            print(page_text[:15000])

            print(
                "\n----- END CURTISS PAGE TEXT -----\n"
            )

            browser.close()

            return (
                None,
                "ZIP accepted, but Curtiss 100+ gallon price was not found."
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
# GENERIC QUOTE PAGE
# =========================================================

def quote_page_100_plus(
    url,
    supplier_name
):

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

                response_url = response.url.lower()

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

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(5000)

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

                    locator = page.locator(selector)

                    if locator.count() > 0:

                        zip_box = locator.first
                        break

                except Exception:
                    continue

            if zip_box is None:

                raise RuntimeError(
                    f"{supplier_name} ZIP input not found"
                )

            zip_box.fill(ZIP)

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

                    locator = page.locator(selector)

                    if locator.count() > 0:

                        check_button = locator.first
                        break

                except Exception:
                    continue

            if check_button is not None:

                try:

                    check_button.click()

                    page.wait_for_timeout(10000)

                except Exception:
                    pass

            for frame in page.frames:

                try:

                    body = frame.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    )

                    body = clean_text(body)

                    if body:
                        diagnostic_text.append(body)

                    price = extract_100_299_price(body)

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100-299 gallon price"
                        )

                    price = extract_100_149_price(body)

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100-149 gallon price"
                        )

                    price = extract_100_plus_price(body)

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100+ gallon price"
                        )

                except Exception:
                    continue

            for frame in page.frames:

                try:

                    html = frame.content()

                    html_text = clean_text(html)

                    price = extract_100_299_price(
                        html_text
                    )

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100-299 gallon price"
                        )

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

                        response_text = response.text()

                        price = extract_100_299_price(
                            response_text
                        )

                        if price is not None:

                            browser.close()

                            return (
                                price,
                                "ZIP-specific 100-299 gallon price"
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
                f"\n----- {supplier_name.upper()} PAGE TEXT -----\n"
            )

            print(
                "\n\n".join(
                    diagnostic_text
                )[:15000]
            )

            print(
                f"\n----- END {supplier_name.upper()} PAGE TEXT -----\n"
            )

            browser.close()

            return (
                None,
                "ZIP accepted, but price was not found."
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

    text = soup_text(
        "https://www.incredibleoil.com/home-heating-oil/"
    )

    price = extract_100_299_price(text)

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

    url = "https://www.fjboil.com/get-price/"

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

                response_url = response.url.lower()

                if any(
                    term in response_url
                    for term in [
                        "price",
                        "quote",
                        "fuel",
                        "product",
                        "order",
                        "api",
                        "ajax"
                    ]
                ):

                    network_responses.append(response)

            except Exception:
                pass

        page.on(
            "response",
            handle_response
        )

        diagnostic_text = []

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            # -------------------------------------------------
            # SELECT HEATING OIL
            # -------------------------------------------------

            selected = False

            select_locators = page.locator("select")

            for i in range(
                select_locators.count()
            ):

                select = select_locators.nth(i)

                try:

                    options = select.locator("option")

                    for j in range(
                        options.count()
                    ):

                        option_text = clean_text(
                            options.nth(j).inner_text()
                        )

                        if "heating oil" in option_text.lower():

                            try:

                                select.select_option(
                                    label=option_text
                                )

                                selected = True

                                break

                            except Exception:

                                option_value = (
                                    options.nth(j)
                                    .get_attribute("value")
                                )

                                if option_value:

                                    select.select_option(
                                        value=option_value
                                    )

                                    selected = True
                                    break

                except Exception:
                    continue

                if selected:
                    break

            # -------------------------------------------------
            # CUSTOM DROPDOWN FALLBACK
            # -------------------------------------------------

            if not selected:

                try:

                    combobox = page.locator(
                        '[role="combobox"]'
                    )

                    for i in range(
                        combobox.count()
                    ):

                        combo = combobox.nth(i)

                        try:

                            combo.click()

                            page.wait_for_timeout(500)

                            option = page.locator(
                                '[role="option"]:has-text("Heating Oil")'
                            )

                            if option.count() > 0:

                                option.first.click()

                                selected = True
                                break

                        except Exception:
                            continue

                except Exception:
                    pass

            # -------------------------------------------------
            # ZIP
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

                    locator = page.locator(selector)

                    if locator.count() > 0:

                        zip_box = locator.first
                        break

                except Exception:
                    continue

            if zip_box is None:

                raise RuntimeError(
                    "FJ Boil ZIP input not found"
                )

            zip_box.fill(ZIP)

            # -------------------------------------------------
            # GET PRICE
            # -------------------------------------------------

            button_selectors = [
                'button:has-text("Get Price")',
                'button:has-text("Get price")',
                'button:has-text("Check Price")',
                'button:has-text("Check price")',
                'button:has-text("Check")',
                'button:has-text("Price")',
                'input[type="submit"]',
            ]

            price_button = None

            for selector in button_selectors:

                try:

                    locator = page.locator(selector)

                    if locator.count() > 0:

                        price_button = locator.first
                        break

                except Exception:
                    continue

            if price_button is None:

                raise RuntimeError(
                    "FJ Boil Get Price button not found"
                )

            price_button.click()

            page.wait_for_timeout(10000)

            # -------------------------------------------------
            # PAGE TEXT
            # -------------------------------------------------

            for frame in page.frames:

                try:

                    body = frame.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    )

                    body = clean_text(body)

                    if body:
                        diagnostic_text.append(body)

                    price = extract_100_299_price(body)

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100-299 gallon price"
                        )

                except Exception:
                    continue

            # -------------------------------------------------
            # HTML
            # -------------------------------------------------

            for frame in page.frames:

                try:

                    html = frame.content()

                    html_text = clean_text(html)

                    price = extract_100_299_price(
                        html_text
                    )

                    if price is not None:

                        browser.close()

                        return (
                            price,
                            "ZIP-specific 100-299 gallon price"
                        )

                except Exception:
                    continue

            # -------------------------------------------------
            # NETWORK
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

                        response_text = response.text()

                        price = extract_100_299_price(
                            response_text
                        )

                        if price is not None:

                            browser.close()

                            return (
                                price,
                                "ZIP-specific 100-299 gallon price"
                            )

                except Exception:
                    continue

            print(
                "\n----- FJ BOIL PAGE TEXT -----\n"
            )

            print(
                "\n\n".join(
                    diagnostic_text
                )[:15000]
            )

            print(
                "\n----- END FJ BOIL PAGE TEXT -----\n"
            )

            browser.close()

            return (
                None,
                "Heating Oil selected/ZIP entered, but 100-299 gallon price was not found."
            )

        except Exception as error:

            try:
                browser.close()
            except Exception:
                pass

            return (
                None,
                "FJ Boil quote failed: "
                + type(error).__name__
                + ": "
                + str(error)[:250]
            )


# =========================================================
# EASY OIL
# =========================================================

def easy_oil_ct():

    text = soup_text(
        "https://www.easyoilct.com/"
    )

    price = extract_100_299_price(text)

    if price is not None:

        return (
            price,
            "Published 100-299 gallon homepage price"
        )

    price = extract_100_plus_price(text)

    if price is not None:

        return (
            price,
            "Published 100+ gallon homepage price"
        )

    price = extract_100_gallon_price(text)

    if price is not None:

        return (
            price,
            "Published 100-gallon homepage price"
        )

    raise RuntimeError(
        "Could not find Easy Oil homepage price"
    )


# =========================================================
# G&G OIL
# =========================================================

def gg_oil_ct():

    return quote_page_100_plus(
        "https://www.ggoilct.com/",
        "GG Oil CT"
    )


# =========================================================
# OMNI ENERGY
# =========================================================

def omni_energy():

    text = soup_text(
        "https://myomnienergy.com/"
    )

    price = extract_100_299_price(text)

    if price is not None:

        return (
            price,
            "Published 100-299 gallon homepage price"
        )

    price = extract_100_149_price(text)

    if price is not None:

        return (
            price,
            "Published 100-149 gallon homepage price"
        )

    price = extract_100_plus_price(text)

    if price is not None:

        return (
            price,
            "Published 100+ gallon homepage price"
        )

    price = extract_100_gallon_price(text)

    if price is not None:

        return (
            price,
            "Published 100-gallon homepage price"
        )

    raise RuntimeError(
        "Could not find Omni Energy homepage price"
    )


# =========================================================
# PURPLE FUELS
# =========================================================

def purple_fuels():

    text = soup_text(
        "https://www.purplefuels.com/"
    )

    price = extract_100_299_price(text)

    if price is not None:

        return (
            price,
            "Published 100-299 gallon homepage price"
        )

    raise RuntimeError(
        "Could not find Purple Fuels 100-299 gallon homepage price"
    )


# =========================================================
# IT ENERGY
# =========================================================

def it_energy():

    text = soup_text(
        "https://itenergyllc.com/"
    )

    patterns = [
        r"(?:today'?s|day'?s)\s+price\s*:\s*\$\s*(\d+\.\d{2,3})",
        r"(?:today'?s|day'?s)\s+price.{0,100}?\$\s*(\d+\.\d{2,3})",
        r"\$\s*(\d+\.\d{2,3}).{0,100}?(?:minimum|100)\s*gallons?",
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
                "Published homepage price; 100-gallon minimum"
            )

    price = extract_100_gallon_price(text)

    if price is not None:

        return (
            price,
            "Published 100-gallon minimum homepage price"
        )

    raise RuntimeError(
        "Could not find IT Energy homepage price"
    )


# =========================================================
# FEDERAL OIL
# =========================================================

def federal_oil():

    text = soup_text(
        "https://federal-oil.com/"
    )

    patterns = [
        r"Cash\s+Price\s*:\s*\$\s*(\d+\.\d{2,3})",
        r"Cash\s+Price.{0,100}?\$\s*(\d+\.\d{2,3})",
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
                "Published homepage cash price"
            )

    raise RuntimeError(
        "Could not find Federal Oil homepage cash price"
    )


# =========================================================
# DIME OIL
# =========================================================

def dime_oil():

    text = soup_text(
        "https://www.dimeoilco.com/"
    )

    patterns = [
        r"Today's\s+Price\s*:\s*\$\s*(\d+\.\d{2,3})",
        r"Today'?s\s+Price.{0,100}?\$\s*(\d+\.\d{2,3})",
        r"\$\s*(\d+\.\d{2,3}).{0,150}?Home\s+Heating\s+Oil\s+for\s+150\s+gallons?",
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
                "Published 150+ gallon homepage price"
            )

    raise RuntimeError(
        "Could not find Dime Oil homepage price"
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
            "https://www.fjboil.com/get-price/",
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

        run_supplier(
            "Omni Energy",
            "https://myomnienergy.com/",
            omni_energy
        ),

        run_supplier(
            "Purple Fuels",
            "https://www.purplefuels.com/",
            purple_fuels
        ),

        run_supplier(
            "IT Energy",
            "https://itenergyllc.com/",
            it_energy
        ),

        run_supplier(
            "Federal Oil",
            "https://federal-oil.com/",
            federal_oil
        ),

        run_supplier(
            "Dime Oil",
            "https://www.dimeoilco.com/",
            dime_oil
        ),
    ]


    # =========================================================
    # SORT CHEAPEST FIRST
    # =========================================================

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