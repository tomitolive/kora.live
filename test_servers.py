import sys
import os
sys.path.append(os.path.join(os.getcwd(), "cuplive"))
import asyncio
import logging
from scraper import CupLiveScraper

async def test():
    logging.basicConfig(level=logging.INFO)
    scraper = CupLiveScraper()
    url = "https://a10.sia-koora.live/on-time/"
    print(f"Testing extraction on: {url}")
    
    # We'll use a modified version of the scraper logic to test this specific URL
    # since scrape_match_stream normally looks for a match name first.
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            sources = []
            from urllib.parse import urljoin
            
            for frame in page.frames:
                try:
                    menu_links = await frame.query_selector_all(".aplr-menu a.aplr-link, ul.aplr-menu li a")
                    for link in menu_links:
                        href = await link.get_attribute("href")
                        text = await link.inner_text()
                        if href and href != "#":
                            full_url = urljoin(frame.url, href)
                            if not any(s['url'] == full_url for s in sources):
                                sources.append({
                                    "name": text.strip() or f"سيرفر {len(sources)+1}", 
                                    "url": full_url
                                })
                except:
                    continue
            
            print("\nFOUND SOURCES:")
            for s in sources:
                print(f"- {s['name']}: {s['url']}")
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
