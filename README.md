# 06712 Heating Oil Price Dashboard

A small dashboard for comparing 100-gallon heating-oil prices for ZIP 06712.

## Sources
- First Fuel Oil — https://www.firstfueloil.com/
- Phillips Oil & Propane — https://phillipsoilllc.com/
- Curtiss Oil — https://curtissoil.com/
- Incredible Oil & Propane — https://www.incredibleoil.com/

## Architecture
The dashboard is static HTML/JS. A GitHub Actions job runs every 6 hours, executes
`scraper.py`, and writes `data/prices.json`. GitHub Pages can then serve the dashboard.

The scraper is intentionally conservative: if a source cannot be parsed, it records
the source as unavailable rather than inventing a price.

## Deploy
1. Create a GitHub repository and upload these files.
2. In Settings -> Pages, select "Deploy from a branch", branch `main`, folder `/root`.
3. In Settings -> Actions -> General, allow Actions to read/write repository contents.
4. Run the "Update heating oil prices" workflow once manually.
5. GitHub Pages will give you the public dashboard URL.

The workflow is scheduled every 6 hours. GitHub may delay scheduled jobs by a few
minutes, so "every 6 hours" is approximate.

## Important
Some oil-company sites use JavaScript or checkout widgets to calculate ZIP-specific
prices. The scraper includes adapters for the public pricing pages and a generic
fallback, but a site can change its markup at any time. The dashboard shows the
source URL and timestamp so you can verify a quote before ordering.
