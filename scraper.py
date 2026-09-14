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


# ---------------------------------------------------------
# FIRST FUEL OIL
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# PHILLIPS OIL
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# CURTISS OIL
# ---------------------------------------------------------

def extract_curtiss_price_from_text(text):
    """
    Look specifically for the Curtiss '100+ gallons'
    pricing tier.

    We intentionally do NOT require an exact
    '100 gallons' row because Curtiss uses
    '100+ gallons'.
    """

    text = clean_text(text)

    # Normalize common variations:
    # 100+ gallons
    # 100 + gallons
    # 100+ gallon
    # 100 + gallon
    patterns = [

        # Price immediately after 100+ gallons
        r"100\s*\+\s*gallons?.{0,250}?\$\s*(\d+\.\d{2,3})",

        # Price immediately before 100+ gallons
        r"\$\s*(\d+\.\d{2,3}).{0,250}?100\s*\+\s*gallons?",

        # Some pages may use "100+ gal"
        r"100\s*\+\s*gal(?:lon)?s?.{0,250}?\$\s*(\d+\.\d{2,3})",

        # Extra fallback for "100 +"
        r"100\s*\+\s*.{0,150}?\$\s*(\d+\.\d{2,3})",
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


def extract_curtiss_price_from_page(page):
    """
    Search the main page and all frames for the
    100+ gallons price.
    """

    # First search every frame's visible text.
    for frame in page.frames:

        try:
            body = frame.locator(
                "body"
            ).inner_text(
                timeout=5000
            )

            body = clean_text(body)

            price = extract_curtiss_price_from_text(
                body
            )

            if price is not None:
                return price, body

        except Exception:
            continue

    # Search HTML as an additional fallback.
    for frame in page.frames:

        try:
            html = frame.content()

            price = extract_curtiss_price_from_text(
                clean_text(html)
            )

            if price is not None:
                return price, clean_text(html)

        except Exception:
            continue

    return None, ""


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

        # Keep track of network responses in case
        # Curtiss loads pricing through an API.
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

            # -------------------------------------------------
            # Load Curtiss quote page
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
            # Find ZIP field
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

            # -------------------------------------------------
            # Enter ZIP
            # -------------------------------------------------

            zip_box.fill(
                ZIP
            )

            # -------------------------------------------------
            # Find Check Price button
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

            # -------------------------------------------------
            # Submit ZIP
            # -------------------------------------------------

            check_button.click()

            # Give the quote application time to load.
            page.wait_for_timeout(
                10000
            )

            # -------------------------------------------------
            # Search for "100+ gallons"
            # -------------------------------------------------

            price, page_text = (
                extract_curtiss_price_from_page(
                    page
                )
            )

            if price is not None:

                browser.close()

                return (
                    price,
                    "ZIP-specific 100+ gallon price"
                )

            # -------------------------------------------------
            # Network/API fallback
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

                        price = (
                            extract_curtiss_price_from_text(
                                response_text
                            )
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
            # Diagnostic output
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

            print(
                "\n----- CURTISS FRAMES -----\n"
            )

            for index, frame in enumerate(
                page.frames
            ):

                try:

                    frame_text = frame.locator(
                        "body"
                    ).inner_text(
                        timeout=3000
                    )

                    print(
                        f"\n--- FRAME {index} ---\n"
                    )

                    print(
                        clean_text(
                            frame_text
                        )[:5000]
                    )

                except Exception:
                    pass

            print(
                "\n----- END CURTISS FRAMES -----\n"
            )

            browser.close()

            return (
                None,
                "ZIP accepted, but Curtiss 100+ gallon price was not found. Check the Actions log for the Curtiss page/frame text."
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


# ---------------------------------------------------------
# INCREDIBLE OIL
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# SUPPLIER RUNNER
# ---------------------------------------------------------

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

        # Important:
        # Curtiss may return None when it cannot find
        # the price. Do NOT call round(None, 3).

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


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

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
