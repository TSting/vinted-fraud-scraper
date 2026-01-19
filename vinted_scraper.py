import asyncio
import os
import time
from playwright.async_api import async_playwright
try:
    from playwright_stealth import stealth_async
except ImportError:
    # Fallback for different versions
    try:
        from playwright_stealth import Stealth
        async def stealth_async(page):
            await Stealth().apply_stealth_async(page)
    except ImportError:
        async def stealth_async(page):
            pass

VINTED_SEARCH_URL = "https://www.vinted.nl/catalog?status_ids%5B%5D=6&page=1&time=1768305966&brand_ids%5B%5D=40883&search_by_image_uuid=&order=newest_first"

async def capture_newest_vinted_item_screenshot(output_dir: str = "vinted_screenshots"):
    """
    Goes to the Vinted search URL, opens the first item, and takes a screenshot.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    timestamp = int(time.time())
    screenshot_path = os.path.join(output_dir, f"vinted_item_{timestamp}.png")

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth
        await stealth_async(page)

        try:
            # 1. Navigate to URL
            print(f"Navigating to {VINTED_SEARCH_URL}")
            await page.goto(VINTED_SEARCH_URL, wait_until="networkidle")

            # 2. Handle Cookies - Try multiple buttons
            cookie_buttons = ["Alle toestaan", "Accepteren", "Accept all", "Toestaan"]
            for btn_name in cookie_buttons:
                btn = page.get_by_role("button", name=btn_name)
                if await btn.is_visible():
                    print(f"Accepting cookies with button: {btn_name}")
                    await btn.click()
                    await asyncio.sleep(1) # Wait for fade out
                    break
            
            # 3. Find and click the first item
            print("Looking for the first item...")
            first_item = page.locator('[data-testid="grid-item"]').first
            await first_item.wait_for(state="visible", timeout=10000)
            
            # Scroll to it to make sure it's clickable
            await first_item.scroll_into_view_if_needed()
            
            print("Clicking the first item...")
            await first_item.click()

            # 4. Wait for product page
            print("Waiting for product page to load...")
            await page.wait_for_load_state("load")
            await page.wait_for_load_state("networkidle")
            
            try:
                await page.wait_for_selector('h1, [data-testid="item-description"], .item-attributes', timeout=15000)
                print("Product page content detected.")
            except:
                print("Warning: Specific product selectors not found, proceeding with screenshot anyway.")

            # 5. Take screenshot of the product element specifically
            print(f"Taking screenshot: {screenshot_path}")
            await asyncio.sleep(2) # Extra buffer for images to render
            
            # Hide noise elements like headers, footers, and cookie banners to keep the screenshot clean
            # Also try to reset body/html margins to minimize white space
            await page.add_style_tag(content="""
                header, footer, .sidebar, .ads, #onetrust-banner-sdk, 
                .is-header-sticky, .notification-manager, 
                .catalog-filter-modal, .cookie-consent,
                .details-list__item--seller { display: none !important; }
                
                /* Force content to be more compact for the screenshot */
                body, html { margin: 0 !important; padding: 0 !important; }
                .item-view__main, .item-main-container { width: 100% !important; max-width: 100% !important; margin: 0 !important; }
            """)
            
            # Try to find a good container for the screenshot to avoid whitespace
            # We prioritize elements that closely wrap the product images and details
            container_selectors = [
                'div[data-testid="item-view"]', # Specific Vinted view
                '.item-view',
                '.item-view__main',
                '.item-main-container',
                'main', 
                '.item-content',
                '[data-testid="item-details"]',
                '.main-content',
                '.item-container',
            ]
            
            target_element = None
            for selector in container_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        # Check if the element has weight/height to avoid capturing empty shells
                        box = await element.bounding_box()
                        if box and box['width'] > 100 and box['height'] > 100:
                            print(f"Targeting element for screenshot: {selector}")
                            target_element = element
                            break
                except:
                    continue

            if target_element:
                # We found a target! Let's scroll it into view and take the screenshot
                await target_element.scroll_into_view_if_needed()
                await asyncio.sleep(1) # Final render buffer
                
                # If the container is too wide, we try to clip it to the content
                await target_element.screenshot(path=screenshot_path)
            else:
                print("Warning: No specific product container found, falling back to full page screenshot.")
                # We still hide headers/footers for the full page screenshot if possible
                await page.screenshot(path=screenshot_path, full_page=False)
            
            return screenshot_path, page.url

        except Exception as e:
            print(f"Error during scraping: {e}")
            # Fallback screenshot on error
            error_screenshot = os.path.join(output_dir, f"error_{timestamp}.png")
            await page.screenshot(path=error_screenshot)
            raise e
        finally:
            await browser.close()

if __name__ == "__main__":
    # Test run
    path, url = asyncio.run(capture_newest_vinted_item_screenshot())
    print(f"Success! Screenshot saved to {path} for product {url}")
