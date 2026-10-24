import json

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/"
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto(URL, wait_until="networkidle", timeout=20000)
    page.wait_for_timeout(1200)
    api = page.request.get(URL + "api/lab/models", timeout=10000)
    payload = api.json()
    print("page_status", response.status if response else None)
    print("title", page.title())
    print("model_api_status", api.status)
    print("gate2_models", len(payload.get("models", [])))
    print(
        "selects",
        page.locator("select").count(),
        "buttons",
        page.locator("button").count(),
    )
    print("best_text_matches", page.get_by_text("best", exact=False).count())
    print("page_errors", json.dumps(errors))
    if not response or response.status != 200:
        raise SystemExit("dashboard page request failed")
    if api.status != 200 or len(payload.get("models", [])) != 56:
        raise SystemExit("expected all 56 Gate 2 models from the API")
    if errors:
        raise SystemExit(f"uncaught page errors: {errors}")
    browser.close()
