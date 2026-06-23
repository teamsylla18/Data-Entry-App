# Vendor Assets

All third-party assets are vendored locally. No CDN references are permitted
anywhere in this project — the app must work fully offline.

| File | Package | Version |
|------|---------|----------|
| bootstrap.min.css | Bootstrap | 5.3.2 |
| bootstrap.bundle.min.js | Bootstrap + Popper | 5.3.2 |
| alpine.min.js | Alpine.js | 3.13.3 |
| chart.min.js | Chart.js | 4.4.1 |

To update an asset, download the new version and replace the file here.
Run `python check_offline.py` after any template/static change to verify
no external URLs have been introduced.
