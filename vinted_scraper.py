import asyncio
import os
import time
import re
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

import json

HISTORY_FILE = "seller_history.json"

def load_seller_history():
    """Loads the seller history from a JSON file."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")
    return {"sellers": {}}

def save_seller_history(history):
    """Saves the seller history to a JSON file."""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"Error saving history: {e}")

def cleanup_seller_history(history):
    """Removes items older than 24 hours from the history."""
    now = time.time()
    cutoff = now - (24 * 3600)
    
    new_sellers = {}
    for seller, items in history.get("sellers", {}).items():
        # Keep only items added within the last 24h
        valid_items = [item for item in items if item.get("added_at", 0) > cutoff]
        if valid_items:
            new_sellers[seller] = valid_items
            
    history["sellers"] = new_sellers
    return history

async def get_seller_info(page):
    """
    Extracts the seller's username and profile URL from the product page.
    Returns: (name, url)
    """
    seller_name = None
    seller_url = None
    try:
        # Strategy 1: Specific data-testid (Reliable but potentially delayed)
        # Wait a bit for the element to be present
        selectors = [
            '[data-testid="profile-username"]',
            '[data-testid="item-owner-name"]',
            '.seller-details__name',
            'a[href*="/member/"]'
        ]
        
        for selector in selectors:
            try:
                # Use a short wait to ensure JS has rendered the name
                el = page.locator(selector).first
                await el.wait_for(state="visible", timeout=3000)
                
                # Check if it's a link to get URL
                href = await el.get_attribute('href')
                if not href:
                    # Look for parent link or link inside
                    link_el = page.locator(f'a:has({selector}), {selector} a').first
                    if await link_el.count() > 0:
                        href = await link_el.get_attribute('href')

                if href:
                    seller_url = f"https://www.vinted.nl{href}" if href.startswith('/') else href

                name = await el.inner_text()
                if name and len(name.strip()) > 1:
                    # Clean up: sometimes it has reviews or " (90)"
                    seller_name = name.splitlines()[0].split('(')[0].strip()
                    if seller_name and seller_url:
                        return seller_name, seller_url
            except:
                continue
        
        # Strategy 2: Extract from profile link URL specifically
        profile_links = await page.locator('a[href*="/member/"]').all()
        for link in profile_links:
            href = await link.get_attribute('href')
            if href and "signup" not in href and "login" not in href:
                seller_url = f"https://www.vinted.nl{href}" if href.startswith('/') else href
                parts = href.strip('/').split('/')
                if len(parts) >= 2 and parts[0] == 'member':
                    member_part = parts[1]
                    if '-' in member_part:
                        seller_name = member_part.split('-', 1)[1]
                    else:
                        seller_name = member_part
                    return seller_name, seller_url

        return seller_name, seller_url
    except Exception as e:
        print(f"Error extracting seller info: {e}")
        return None, None

async def get_item_details(page):
    """
    Extracts Size, Color and Product ID (if available) from the item page.
    """
    details = {
        "size": "Onbekend",
        "color": "Onbekend",
        "product_id": "Onbekend"
    }
    try:
        # 1. Attributes from the details list
        # Use a shorter timeout to avoid hanging
        try:
            attr_elements = await page.locator('.details-list__item').all()
            for el in attr_elements:
                try:
                    text = await el.inner_text(timeout=5000)
                    if '\n' in text:
                        key, value = text.split('\n', 1)
                        key_l = key.lower()
                        if 'maat' in key_l or 'size' in key_l:
                            details["size"] = value.strip()
                        elif 'kleur' in key_l or 'color' in key_l:
                            details["color"] = value.strip()
                except:
                    continue
        except Exception as e:
            print(f"Warning: Could not extract attributes: {e}")

        # 2. Try to find Product ID/Article Code in description
        try:
            # Check for description
            desc_loc = page.locator('[data-testid="item-description"]')
            description = await desc_loc.inner_text(timeout=5000)
            
            # Check for title
            title_loc = page.locator('h1')
            title = await title_loc.inner_text(timeout=5000)
            
            combined_text = f"{title} {description}"
            
            # Look for patterns like "Art: 1234567" or just 7-10 digit numbers
            # Common Costes patterns: 1234567, 1.23.4.5678, or 123456-123
            potential_ids = re.findall(r'\b\d{7,10}\b|\b\d{6}-\d{3}\b', combined_text)
            if potential_ids:
                details["product_id"] = potential_ids[0]
            else:
                # Check for dotted format
                dotted_ids = re.findall(r'\b\d\.\d{2}\.\d\.\d{4}\b', combined_text)
                if dotted_ids:
                    details["product_id"] = dotted_ids[0]
        except Exception as e:
            print(f"Warning: Could not extract ID from description: {e}")

    except Exception as e:
        print(f"Error in get_item_details: {e}")
    
    return details

async def capture_newest_vinted_item_screenshot(output_dir: str = "vinted_screenshots"):
    """
    Goes to the Vinted search URL, opens items from the last 24h, and takes a screenshot if seller matches.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 0. Load and cleanup persistent history
    history = load_seller_history()
    history = cleanup_seller_history(history)
    print(f"Loaded history for {len(history['sellers'])} sellers.")

    timestamp = int(time.time())
    # Note: screenshot_path will now be generated per-item to ensure uniqueness

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
            print(f"Scanning up to {len(candidate_urls)} items from the last 24h...")
            
            success_match = False
            match_count = 0
            all_matches = []

            for idx, product_url in enumerate(candidate_urls):
                print(f"\n--- Scanning Item {idx+1}/{len(candidate_urls)} ---")
                print(f"URL: {product_url}")
                
                try:
                    await page.goto(product_url, wait_until="load")
                    
                    try:
                        await page.wait_for_selector('h1, [data-testid="item-description"], .item-attributes', timeout=10000)
                    except:
                        print("Page load timeout, skipping...")
                        continue

                    # 4.1 Check 24h time limit
                    is_fresh, time_text = await check_is_within_24h(page)
                    if not is_fresh:
                        print(f"⛔ Item is too old ({time_text}). Stopping scan as list is sorted by date.")
                        break # STOP the loop
                    
                    print(f"✓ Item is recent ({time_text}).")

                    # 4.1.b Get extra details
                    item_details = await get_item_details(page)

                    # 4.2 Get Seller Info
                    seller_name, seller_url = await get_seller_info(page)
                    if not seller_name:
                        print("Could not identify seller. Skipping.")
                        continue
                        
                    print(f"Seller: {seller_name} ({seller_url})")
                    
                    # 4.3 Update History
                    if seller_name not in history["sellers"]:
                        history["sellers"][seller_name] = []
                    
                    # Add current item to history if not exists
                    exists = any(item["url"] == product_url for item in history["sellers"][seller_name])
                    if not exists:
                        history["sellers"][seller_name].append({
                            "url": product_url,
                            "added_at": time.time()
                        })
                        print(f"Item added to history for {seller_name}.")
                    
                    seller_count = len(history["sellers"][seller_name])
                    print(f"Seller '{seller_name}' now has {seller_count} detected items in rolling 24h.")
                    
                    # 4.4 Check Criteria (Total >= 3 items in history)
                    if seller_count >= 3:
                        # Generate unique screenshot path for this specific item
                        item_id = product_url.split('/items/')[1].split('-')[0] if '/items/' in product_url else str(int(time.time()))
                        current_screenshot_path = os.path.join(output_dir, f"vinted_item_{item_id}.png")
                        
                        # Take screenshot
                        print(f"Taking screenshot: {current_screenshot_path}")
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
                            await target_element.screenshot(path=current_screenshot_path)
                        else:
                            await page.screenshot(path=current_screenshot_path, full_page=False)

                        success_match = True
                        match_count += 1
                        all_matches.append({
                            "url": product_url,
                            "screenshot_path": current_screenshot_path,
                            "seller_name": seller_name,
                            "seller_url": seller_url,
                            "seller_count": seller_count,
                            "item_id": item_id,
                            "size": item_details["size"],
                            "color": item_details["color"],
                            "product_id": item_details["product_id"]
                        })
                        # Continue scanning other items
                        print(f"Match recorded for {seller_name}. Continuing scan...")
                    
                except Exception as e:
                    print(f"Error processing item {idx}: {e}")
                    continue

            # Save updated history before exiting
            save_seller_history(history)

            if not success_match:
                 print("\nScanned all recent items. No seller found with >= 3 items in rolling 24h.")
                 await browser.close()
                 return []
            
            print(f"\nScan complete. Found {match_count} matches.")
            return all_matches

        except Exception as e:
            print(f"Error during scraping: {e}")
            raise e
        finally:
            await browser.close()

if __name__ == "__main__":
    path, url = asyncio.run(capture_newest_vinted_item_screenshot())
    if path:
        print(f"Success to {path}")
