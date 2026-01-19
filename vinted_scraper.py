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

async def check_seller_has_multiple_costes_items(page, min_other_items: int = 2):
    """
    Checks if the seller of the current item has at least min_other_items other Costes items.
    
    Args:
        page: Playwright page object (should be on a product detail page)
        min_other_items: Minimum number of OTHER Costes items the seller should have (default: 2)
    
    Returns:
        bool: True if seller has enough items, False otherwise
    """
    try:
        print(f"Checking if seller has at least {min_other_items} other Costes items...")
        
        # Find the seller profile link on the product page
        # We need to be more specific to avoid signup links
        seller_link_selectors = [
            'a.details-list__item-link[href*="/member/"]',  # More specific selector
            'a[href*="/member/"]:not([href*="signup"])',    # Exclude signup links
            '[data-testid="user-profile-link"]',
            'a.user-login'
        ]
        
        seller_url = None
        for selector in seller_link_selectors:
            try:
                # Get all matching elements
                elements = await page.locator(selector).all()
                for element in elements:
                    url = await element.get_attribute('href')
                    # Filter out signup and invalid URLs
                    if url and '/member/' in url and 'signup' not in url:
                        seller_url = url
                        print(f"Found seller profile link: {seller_url}")
                        break
                if seller_url:
                    break
            except:
                continue
        
        if not seller_url:
            print("Warning: Could not find seller profile link")
            return False
        
        # Make sure we have a full URL
        if seller_url.startswith('/'):
            seller_url = f"https://www.vinted.nl{seller_url}"
        
        # Navigate to seller's profile with Costes brand filter AND 'Nieuw met prijskaartje' status
        # Brand ID 40883 is Costes
        # Status ID 6 is 'Nieuw met prijskaartje' (New with tags)
        seller_costes_url = f"{seller_url}/items?brand_ids[]=40883&status_ids[]=6"
        print(f"Navigating to seller's Costes items (Nieuw met prijskaartje): {seller_costes_url}")
        
        await page.goto(seller_costes_url, wait_until="load")
        await asyncio.sleep(1)
        
        # Check for "No items" text first
        # Vinted often explains "Geen artikelen gevonden" or "No items found"
        content_text = await page.content()
        if "Geen artikelen gevonden" in content_text or "No items found" in content_text:
             print("Seller has 0 matching items (found 'No items' text).")
             return False

        # Count the number of Costes items
        items = await page.locator('[data-testid="grid-item"]').all()
        item_count = len(items)
        
        print(f"Seller has {item_count} Costes item(s) with 'Nieuw met prijskaartje' status")
        
        # We need at least min_other_items + 1 (the current item we're looking at)
        required_total = min_other_items + 1
        
        if item_count >= required_total:
            print(f"✓ Seller has {item_count} 'Nieuw met prijskaartje' items (>= {required_total} required). Proceeding.")
            return True
        else:
            print(f"✗ Seller only has {item_count} items (< {required_total} required). Skipping.")
            return False
            
    except Exception as e:
        print(f"Error checking seller items: {e}")
        return False

async def check_is_within_24h(page):
    """
    Checks if the item was uploaded within the last 24 hours.
    Returns:
        (bool, str): (is_within_24h, time_text)
        is_within_24h is True if < 24h, False if > 24h, None if undetermined.
    """
    try:
        # Search in the details list for "Geplaatst" or "Uploaded"
        # The structure is usually .details-list__item containing title and value
        details_text = await page.locator('.details-list__item').all_inner_texts()
        
        time_text = "Unknown"
        
        # Look for the line containing the timestamp
        found_timestamp = False
        for text in details_text:
            if "Geplaatst" in text or "Uploaded" in text:
                # The text usually looks like "Geplaatst\n1 uur geleden"
                # We normalize it
                lines = text.split('\n')
                for line in lines:
                    line_lower = line.lower().strip()
                    # Check for time indicators
                    if any(x in line_lower for x in ['zojuist', 'just now', 'minu', 'uur', 'hour', 'ind', 'sec']):
                         time_text = line.strip()
                         found_timestamp = True
                         break
                    if 'dag' in line_lower or 'day' in line_lower:
                         time_text = line.strip()
                         found_timestamp = True
                         break
            if found_timestamp:
                break
        
        print(f"Detected upload time: {time_text}")
        
        if not found_timestamp:
            print("Warning: Could not find specific timestamp, assuming within 24h to be safe.")
            return True, "Unknown"

        time_lower = time_text.lower()
        
        # Logic for < 24h
        # "zojuist", "seconden", "minuten", "uur" (hours) -> Keep
        if any(x in time_lower for x in ['zojuist', 'just now', 'sec', 'min', 'uur', 'hour']):
            return True, time_text
        
        # "dag", "days" -> Stop (older than 24h)
        # Vinted switches to "1 dag geleden" after 24h
        if 'dag' in time_lower or 'day' in time_lower:
            return False, time_text
            
        return True, time_text # Default keep if unsure

    except Exception as e:
        print(f"Error checking time: {e}")
        return True, "Error" # Fail open

async def capture_newest_vinted_item_screenshot(output_dir: str = "vinted_screenshots"):
    """
    Goes to the Vinted search URL, opens items from the last 24h, and takes a screenshot if seller matches.
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

            # 2. Handle Cookies
            cookie_buttons = ["Alle toestaan", "Accepteren", "Accept all", "Toestaan"]
            for btn_name in cookie_buttons:
                btn = page.get_by_role("button", name=btn_name)
                if await btn.is_visible():
                    print(f"Accepting cookies with button: {btn_name}")
                    await btn.click()
                    await asyncio.sleep(2)
                    break
            
            try:
                await page.wait_for_selector('#onetrust-consent-sdk', state='hidden', timeout=3000)
                print("Cookie banner confirmed hidden")
            except:
                print("Cookie banner selector not found or already hidden")
            
            # 3. Collect candidate item URLs
            print("Collecting candidate Costes items from search results...")
            candidate_urls = []
            grid_items = page.locator('[data-testid="grid-item"]')
            count = await grid_items.count()
            print(f"Found {count} items in grid")

            # We collect more items to ensure we verify 24h range
            max_check = 100 
            for i in range(min(count, max_check)): 
                try:
                    item = grid_items.nth(i)
                    text = await item.inner_text()
                    if "costes" not in text.lower():
                        continue
                    
                    link = item.locator('a').first
                    href = await link.get_attribute('href')
                    if href:
                        full_url = f"https://www.vinted.nl{href}" if href.startswith('/') else href
                        if full_url not in candidate_urls:
                            candidate_urls.append(full_url)
                except:
                    continue
            
            print(f"Found {len(candidate_urls)} candidate Costes items to check.")

            if not candidate_urls:
                print("No Costes items found. Exiting.")
                await browser.close()
                return None, None

            # 4. Iterate through items
            success_match = False
            final_screenshot_path = None
            final_product_url = None

            for idx, product_url in enumerate(candidate_urls):
                print(f"\n--- Checking Item {idx+1}/{len(candidate_urls)} ---")
                print(f"URL: {product_url}")
                
                try:
                    await page.goto(product_url, wait_until="load")
                    
                    try:
                        await page.wait_for_selector('h1, [data-testid="item-description"], .item-attributes', timeout=10000)
                    except:
                        print("Page load timeout, skipping...")
                        continue

                    # 4.4. NEW: Check 24h time limit
                    is_fresh, time_text = await check_is_within_24h(page)
                    if not is_fresh:
                        print(f"⛔ Item is too old ({time_text}). Stopping search as list is sorted by date.")
                        break # STOP the loop completely
                    
                    print(f"✓ Item is recent ({time_text}). Checking seller...")

                    # 4.5. Check seller
                    has_enough_items = await check_seller_has_multiple_costes_items(page, min_other_items=2)
                    
                    if has_enough_items:
                        print("✅ MATCH FOUND! Seller meets criteria. Proceeding to screenshot.")
                        
                        if page.url != product_url:
                            print("Returning to product page...")
                            await page.goto(product_url, wait_until="load")
                            await asyncio.sleep(1)

                        # Take screenshot
                        print(f"Taking screenshot: {screenshot_path}")
                        await asyncio.sleep(2)
                        
                        await page.add_style_tag(content="""
                            header, footer, .sidebar, .ads, #onetrust-banner-sdk, 
                            .is-header-sticky, .notification-manager, 
                            .catalog-filter-modal, .cookie-consent,
                            .details-list__item--seller { display: none !important; }
                            body, html { margin: 0 !important; padding: 0 !important; }
                            .item-view__main, .item-main-container { width: 100% !important; max-width: 100% !important; margin: 0 !important; }
                        """)
                        
                        target_element = None
                        container_selectors = [
                            'div[data-testid="item-view"]', '.item-view', '.item-view__main',
                            '.item-main-container', 'main', '.item-content',
                            '[data-testid="item-details"]', '.main-content', '.item-container',
                        ]
                        
                        for selector in container_selectors:
                            try:
                                element = await page.wait_for_selector(selector, timeout=2000)
                                if element:
                                    box = await element.bounding_box()
                                    if box and box['width'] > 100 and box['height'] > 100:
                                        target_element = element
                                        break
                            except:
                                continue

                        if target_element:
                            await target_element.scroll_into_view_if_needed()
                            await asyncio.sleep(1)
                            await target_element.screenshot(path=screenshot_path)
                        else:
                            await page.screenshot(path=screenshot_path, full_page=False)
                        
                        success_match = True
                        final_screenshot_path = screenshot_path
                        final_product_url = product_url
                        break 
                    
                    else:
                        print("❌ Seller criteria NOT met. Checking next item...")
                        continue

                except Exception as e:
                    print(f"Error processing item {idx}: {e}")
                    continue

            if not success_match:
                 print("\nChecked all candidates. No matching items found in the last 24h.")
                 await browser.close()
                 return None, None
            
            return final_screenshot_path, final_product_url

        except Exception as e:
            print(f"Error during scraping: {e}")
            raise e
        finally:
            await browser.close()

if __name__ == "__main__":
    path, url = asyncio.run(capture_newest_vinted_item_screenshot())
    if path:
        print(f"Success to {path}")
