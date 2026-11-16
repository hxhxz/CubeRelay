from playwright.sync_api import sync_playwright


URL = "https://open-parrot.art/cube-relay/console"
CAMERAS = {
    "场景总览": "overview",
    "夹爪特写": "gripper_closeup",
    "魔方特写": "cube_closeup",
    "俯视相机": "top_ortho",
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    def watch_websocket(websocket):
        print(f"websocket={websocket.url}")
        websocket.on("framesent", lambda payload: print(f"framesent={payload}"))
        websocket.on("framereceived", lambda payload: print(f"framereceived={str(payload)[:160]}"))
        websocket.on("close", lambda: print("websocket=closed"))

    page.on("websocket", watch_websocket)
    page.on("pageerror", lambda error: print(f"pageerror={error}"))
    page.goto(URL, wait_until="networkidle", timeout=60_000)
    page.get_by_text("LIVE · REAL MUJOCO RENDERER").wait_for(timeout=30_000)
    for label, expected in CAMERAS.items():
        page.get_by_role("button", name=label, exact=True).click()
        page.wait_for_timeout(2_000)
        actual = page.evaluate(
            "async () => (await (await fetch('/cube-relay/api/m3d/state')).json()).active_camera"
        )
        print(f"{label}: expected={expected} actual={actual}")
        print(f"active_class={page.get_by_role('button', name=label, exact=True).get_attribute('class')}")
    browser.close()
