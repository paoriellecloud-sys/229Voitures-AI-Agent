import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from database import get_connection


# =============================
# PLAYWRIGHT SCRAPER
# =============================

async def scrape_with_playwright(url: str) -> dict:
    """
    Scrapes a vehicle listing using Playwright (handles JavaScript-rendered content).
    Extracts price, mileage, and vehicle details from dynamic pages.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            locale='fr-CA',
        )

        page = await context.new_page()

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)

            # Extract page content after JS execution
            content = await page.content()

            # Extract specific data points
            result = {
                'url': url,
                'content': content[:5000],
                'title': await page.title(),
                'scraped_at': datetime.now().isoformat(),
                'success': True
            }

            # Try to extract price
            try:
                price_selectors = [
                    '[data-testid="price"]',
                    '.price', '#price',
                    '[class*="price"]',
                    '[class*="Prix"]',
                    'span[class*="price"]',
                ]
                for selector in price_selectors:
                    el = await page.query_selector(selector)
                    if el:
                        result['price'] = await el.inner_text()
                        break
            except:
                pass

            # Try to extract mileage
            try:
                km_selectors = [
                    '[data-testid="mileage"]',
                    '[class*="mileage"]',
                    '[class*="kilomet"]',
                    '[class*="odometer"]',
                ]
                for selector in km_selectors:
                    el = await page.query_selector(selector)
                    if el:
                        result['mileage'] = await el.inner_text()
                        break
            except:
                pass

            return result

        except Exception as e:
            return {
                'url': url,
                'success': False,
                'error': str(e),
                'scraped_at': datetime.now().isoformat()
            }
        finally:
            await browser.close()


def scrape_url_playwright(url: str) -> dict:
    """Synchronous wrapper for async Playwright scraper."""
    try:
        return asyncio.run(scrape_with_playwright(url))
    except Exception as e:
        return {'url': url, 'success': False, 'error': str(e)}


# =============================
# BUFFER DB FUNCTIONS
# =============================

def init_inventory_cache():
    """Creates inventory_cache table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            make TEXT,
            model TEXT,
            year TEXT,
            trim TEXT,
            price TEXT,
            mileage TEXT,
            city TEXT,
            province TEXT,
            url TEXT UNIQUE,
            source TEXT,
            raw_content TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scrape_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            status TEXT DEFAULT 'pending',
            results_count INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error TEXT
        )
    ''')
    conn.commit()
    conn.close()


def save_to_cache(vehicle_data: dict):
    """Saves a scraped vehicle to the inventory cache."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO inventory_cache
            (make, model, year, trim, price, mileage, city, province, url, source, raw_content, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            vehicle_data.get('make', ''),
            vehicle_data.get('model', ''),
            vehicle_data.get('year', ''),
            vehicle_data.get('trim', ''),
            vehicle_data.get('price', ''),
            vehicle_data.get('mileage', ''),
            vehicle_data.get('city', ''),
            vehicle_data.get('province', ''),
            vehicle_data.get('url', ''),
            vehicle_data.get('source', ''),
            vehicle_data.get('raw_content', ''),
            datetime.now().isoformat()
        ))
        conn.commit()
    except Exception as e:
        print(f"Cache save error: {e}")
    finally:
        conn.close()


def search_cache(query: str, limit: int = 5) -> list:
    """
    Searches the inventory cache for vehicles matching the query.
    Returns cached results if fresh (less than 6 hours old).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Parse query for make/model/year
    keywords = query.lower().split()

    sql = '''
        SELECT * FROM inventory_cache
        WHERE is_active = 1
        AND scraped_at > datetime('now', '-6 hours')
        AND (
    '''
    conditions = []
    params = []
    for kw in keywords:
        conditions.append('(LOWER(make) LIKE ? OR LOWER(model) LIKE ? OR year LIKE ?)')
        params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%'])

    sql += ' OR '.join(conditions) + ') LIMIT ?'
    params.append(limit)

    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"Cache search error: {e}")
        return []
    finally:
        conn.close()


def get_cache_stats() -> dict:
    """Returns cache statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM inventory_cache WHERE is_active = 1")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM inventory_cache WHERE scraped_at > datetime('now', '-6 hours')")
        fresh = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT source) FROM inventory_cache")
        sources = cursor.fetchone()[0]
        return {'total': total, 'fresh': fresh, 'sources': sources}
    except:
        return {'total': 0, 'fresh': 0, 'sources': 0}
    finally:
        conn.close()


# Initialize on import
init_inventory_cache()