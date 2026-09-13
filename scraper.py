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


# ---------------------------------------------------------
# General helpers
# ---------------------------------------------------------

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
# First Fuel
# ---------------------------------------------------------

def first_fuel():
    html = get_html("https://www.firstfueloil.com/")
    soup = BeautifulSoup(html, "html.parser")

    text = clean_text(soup.get_text(" ", strip=True))

    patterns = [
        r"100\s*[-–—]\s*299\s*Gallons?.{0,150}?\$\s*(\d+\.\d{2,3})",
        r"100\s*[-–—]\s*299.{0,150}?\$\s*(\d+\.\d{2,3})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1)), "Published 100-299 gallon price"

    raise RuntimeError("Could not find First Fuel price")


# ---------------------------------------------------------
# Phillips
# ---------------------------------------------------------

def phillips():
    html = get_html("https://phillipsoilllc.com/")
    soup = BeautifulSoup(html, "html.parser")

    # Look through every table.
    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        for row in rows:
            cells = [
                clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["td", "th"])
            ]

            if not cells:
                continue

            # We want the row beginning with 100.
            if cells[0].strip() == "100":

                # Expected:
                # 100 | $5.390 | $539.00
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
# Curtiss
# ---------------------------------------------------------

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

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            # -------------------------------------------------
            # Find ZIP input
            # -------------------------------------------------

            zip_selectors = [
                'input[name*="zip" i]',
                'input[id*="zip" i]',
                'input[placeholder*="zip" i]',
                'input[aria-label*="zip" i]',
            ]

            zip_box = None

            for selector in zip_selectors:

                locator = page.locator(selector)

                if locator.count() > 0:
                    zip_box = locator.first
                    break

            if zip_box is None:
                raise RuntimeError("ZIP input not found")

            zip_box.fill(ZIP)

            # -------------------------------------------------
            # Click Check Price
            # -------------------------------------------------

            check_selectors = [
                'button:has-text("Check Price")',
                'input[type="submit"]',
                'button:has-text("Check")',
                'button:has-text("Price")',
            ]

            check_button = None

            for selector in check_selectors:

                locator = page.locator(selector)

                if locator.count() > 0:
                    check_button = locator.first
                    break

            if check_button is None:
                raise RuntimeError(
                    "Check Price button not found"
                )

            check_button.click()

            # Give the quote application time to update.
            page.wait_for_timeout(8000)

            # -------------------------------------------------
            # Get all visible text
            # -------------------------------------------------

            body = page.locator("body").inner_text(
                timeout=15000
            )

            body = clean_text(body)

            # -------------------------------------------------
            # Try to find a 100-gallon row
            # -------------------------------------------------

            patterns = [

                # 100 gallons $5.XX
                r"\b100\s*(?:gallons?|gal)\b"
                r".{0,200}?"
                r"\$\s*(\d+\.\d{2,3})",

                # 100 - 199 gallons $5.XX
                r"\b100\s*[-–—]\s*199\b"
                r".{0,200}?"
                r"\$\s*(\d+\.\d{2,3})",

                # 100 - 299 gallons $5.XX
                r"\b100\s*[-–—]\s*299\b"
                r".{0,200}?"
                r"\$\s*(\d+\.\d{2,3})",
            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    body,
                    re.I
                )

                if match:

                    price = float(match.group(1))

                    browser.close()

                    return (
                        price,
                        "ZIP-specific 100-gallon price"
                    )

            # -------------------------------------------------
            # Look through HTML tables
            # -------------------------------------------------

            for table in page.locator("table").all():

                rows = table.locator("tr").all()

                for row in rows:

                    cells = row.locator(
                        "th, td"
                    ).all_inner_texts()

                    cells = [
                        clean_text(x)
                        for x in cells
                    ]

                    if not cells:
                        continue

                    if cells[0] == "100":

                        for cell in cells[1:]:

                            match = re.search(
                                r"\$\s*(\d+\.\d{2,3})",
                                cell
                            )

                            if match:

                                price = float(
                                    match.group(1)
                                )

                                browser.close()

                                return (
                                    price,
                                    "ZIP-specific 100-gallon price"
                                )

            # -------------------------------------------------
            # Diagnostic information
            # -------------------------------------------------

            print(
                "\n----- CURTISS PAGE TEXT -----\n"
            )

            print(body[:12000])

            print(
                "\n----- END CURTISS PAGE TEXT -----\n"
            )

            browser.close()

            return (
                None,
                "ZIP accepted, but 100-gallon price was not found"
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
                + str(error)[:200]
            )


# ---------------------------------------------------------
# Incredible Oil
# ---------------------------------------------------------

def incredible_oil():
    html = get_html(
        "https://www.incredibleoil.com/home-heating-oil/"
    )

    soup = BeautifulSoup(html, "html.parser")

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
        "Could not find Incredible Oil price"
    )


# ---------------------------------------------------------
# Supplier wrapper
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
            + str(error)[:200]
        )

    return result


# ---------------------------------------------------------
# Main
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
