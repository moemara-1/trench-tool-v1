"""Debug: Find the EXACT structure of the Smart Follower element."""
import asyncio
import sys
import os
import re
sys.path.insert(0, '.')
from pathlib import Path

async def debug_structure():
    print("Debugging Element Structure...")
    
    from playwright.async_api import async_playwright
    playwright = await async_playwright().start()
    
    # Setup paths
    extension_base = Path(__file__).parent / "extensions" / "frontrunpro"
    version_folders = [f for f in os.listdir(extension_base) if f[0].isdigit()]
    version_folders.sort(reverse=True)
    extension_path = str(os.path.join(extension_base, version_folders[0]))
    browser_data = str(Path(__file__).parent / ".browser_data")
    
    # Launch
    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=browser_data,
        headless=False,
        args=[f'--disable-extensions-except={extension_path}', f'--load-extension={extension_path}'],
    )
    
    page = await browser.new_page()
    await page.goto("https://x.com/solana", wait_until='domcontentloaded')
    
    print("Waiting 15s for FrontrunPro...")
    await asyncio.sleep(15)
    
    # DUMP EVERYTHING associated with the smart follower count
    print("\n--- Searching for element containing the known count (approx 2390-2400) ---")
    
    # We'll search for elements containing "Smart Followers" text
    elements = await page.get_by_text("Smart Followers", exact=False).all()
    
    print(f"Found {len(elements)} elements with text 'Smart Followers'")
    
    for i, elem in enumerate(elements):
        try:
            html = await elem.evaluate("el => el.outerHTML")
            text = await elem.inner_text()
            print(f"\n[Element {i}]")
            print(f"Text: {text!r}")
            print(f"HTML: {html}")
            # Also get parent HTML to see context
            parent_html = await elem.evaluate("el => el.parentElement.outerHTML")
            print(f"Parent HTML: {parent_html[:200]}...") 
        except Exception as e:
            print(f"Error inspecting element {i}: {e}")

    await browser.close()
    await playwright.stop()
    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(debug_structure())
