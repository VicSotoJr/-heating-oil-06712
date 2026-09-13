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


def page_text(html):
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return response.text


def find_tier_price(html):
    """
    Find a 100-299 gallon price.
    Handles:
      100 - 299 Gallons $5.09
      100–299 Gallons $5.09
      100-299 Gallons: $5.09
    """
    text = page_text(html)

    pattern = (
        r"100\s*[-–—]\s*299\s*"
        r"(?:gallons?|gal)"
        r".{0,150}?"
        r"\$\s*([0-9]+\.[0-9]{2,3})"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return float(match.group(1))

    return None


def first_fuel():
    html = get_page("https://www.firstfueloil.com/")
    price = find_tier_price(html)

    if price is None:
        raise RuntimeError("Could not find First Fuel 100-299 price")

    return price, "Published 100-299 gallon price"


def incredible_oil():
    html = get_page(
        "https://www.incredibleoil.com/home-heating-oil/"
    )
    price = find_tier_price(html)

    if price is None:
        raise RuntimeError(
            "Could not find Incredible Oil 100-299 price"
        )

    return price, "Published 100-299 gallon price"


def interactive_quote(url):
    """
    Uses the supplier's public quote form.

    Enters ZIP 06712 and attempts to select/request
    100 gallons.

    It does NOT:
      - enter personal information
      - enter payment information
      - place an order
      - proceed through checkout
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
                "height": 1000
            }
        )

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(3000)

            # Find ZIP input
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
                browser.close()
                return None, "ZIP input not found"

            zip_box.fill(ZIP)

            # Find Check Price button
            button_selectors = [
                'button:has-text("Check Price")',
                'input[type="submit"]',
                'button:has-text("Check")',
                'button:has-text("Price")',
            ]

            check_button = None

            for selector in button_selectors:
                locator = page.locator(selector)

                if locator.count() > 0:
                    check_button = locator.first
                    break

            if check_button is None:
                browser.close()
                return None, "Check Price button not found"

            check_button.click()

            # Give the quote application time to load
            page.wait_for_timeout(5000)

            # Try to find a gallon quantity field
            gallon_selectors = [
                'input[name*="gallon" i]',
                'input[id*="gallon" i]',
                'input[placeholder*="gallon" i]',
            ]

            gallon_box = None

            for selector in gallon_selectors:
                locator = page.locator(selector)

                if locator.count() > 0:
                    gallon_box = locator.first
                    break

            if gallon_box is not None:
                try:
                    gallon_box.fill(str(GALLONS))
                    page.wait_for_timeout(2000)
                except Exception:
                    pass

            # Try obvious 100-gallon buttons/options
            quantity_selectors = [
                'label:has-text("100")',
                'button:has-text("100")',
                '[role="button"]:has-text("100")',
            ]

            for selector in quantity_selectors:

                locator = page.locator(selector)

                if locator.count() > 0:

                    try:
                        locator.first.click(timeout=2000)
                        page.wait_for_timeout(2000)
                        break
                    except Exception:
                        pass

            # Read everything visible on the page
            body = page.locator("body").inner_text(
                timeout=10000
            )

            # Patterns for per-gallon pricing
            patterns = [

                # 100-199 gallons $5.19
                r"100\s*[-–—]\s*199\s*"
                r"(?:gallons?|gal)"
                r".{0,150}?"
                r"\$\s*([0-9]+\.[0-9]{2,3})",

                # 100-299 gallons $5.19
                r"100\s*[-–—]\s*299\s*"
                r"(?:gallons?|gal)"
                r".{0,150}?"
                r"\$\s*([0-9]+\.[0-9]{2,3})",

                # 100 gallons $5.19
                r"\b100\s*(?:gallons?|gal)\b"
                r".{0,150}?"
                r"\$\s*([0-9]+\.[0-9]{2,3})",
            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    body,
                    re.IGNORECASE | re.DOTALL
                )

                if match:

                    price = float(match.group(1))

                    browser.close()

                    return (
                        price,
                        "ZIP-specific interactive quote"
                    )

            # Sometimes the site shows a total instead.
            total_patterns = [

                r"100\s*(?:gallons?|gal)"
                r".{0,250}?"
                r"total"
                r".{0,100}?"
                r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)",

                r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)"
                r".{0,100}?"
                r"(?:for|/)"
                r".{0,30}?"
                r"100\s*(?:gallons?|gal)",
            ]

            for pattern in total_patterns:

                match = re.search(
                    pattern,
                    body,
                    re.IGNORECASE | re.DOTALL
                )

                if match:

                    total = float(match.group(1))
                    price = round(total / 100, 3)

                    browser.close()

                    return (
                        price,
                        "ZIP-specific quote; total converted"
                    )

            browser.close()

            return (
                None,
                "ZIP accepted, but no 100-gallon price was exposed"
            )

        except Exception as error:

            try:
                browser.close()
            except Exception:
                pass

            return (
                None,
                "Interactive quote failed: "
                + type(error).__name__
            )


def run_supplier(name, url, mode, function=None):

    result = {
        "name": name,
        "url": url,
        "price_per_gallon": None,
        "note": "Unavailable"
    }

    try:

        if mode == "public":
            price, note = function()

        else:
            price, note = interactive_quote(url)

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
            + str(error)[:120]
        )

    return result


def main():

    suppliers = [

        run_supplier(
            "First Fuel Oil",
            "https://www.firstfueloil.com/",
            "public",
            first_fuel
        ),

        run_supplier(
            "Phillips Oil & Propane",
            "https://phillipsoilllc.com/get-price/",
            "interactive"
        ),

        run_supplier(
            "Curtiss Oil",
            "https://curtissoil.com/get-price/",
            "interactive"
        ),

        run_supplier(
            "Incredible Oil & Propane",
            "https://www.incredibleoil.com/home-heating-oil/",
            "public",
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
