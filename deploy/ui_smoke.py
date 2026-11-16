from playwright.sync_api import sync_playwright


URL = "https://open-parrot.art/cube-relay/console"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", lambda message: print(f"console[{message.type}]: {message.text}"))
    page.on("pageerror", lambda error: print(f"pageerror: {error}"))
    page.on("websocket", lambda websocket: print(f"websocket: {websocket.url}"))
    response = page.goto(URL, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(8_000)
    print(f"http_status={response.status if response else 'none'}")
    print(f"url={page.url}")
    print(f"body={page.locator('body').inner_text()[:2000]}")
    page.screenshot(path="/tmp/cube-relay-console.png", full_page=True)
    browser.close()
