#!/usr/bin/env python3
"""
DJI DRONES BOT - DJI Mini 2 & Mini 2 SE Only
Flow: Price Filter → Title Filter → Green Light → Scrape Description → Quality Check → Discord
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from bs4 import BeautifulSoup
import uvicorn

try:
    from vinted_scraper import AsyncVintedScraper
    VINTED_AVAILABLE = True
except ImportError:
    VINTED_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ vinted_scraper not installed - using mock mode")
    
    class AsyncVintedScraper:
        def __init__(self, baseurl):
            self.baseurl = baseurl
        async def search(self, params):
            logger.warning("⚠️ Mock mode - no real scraping")
            return []

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="DJI Drones Bot")
DATABASE_FILE = "dji_drones_bot.db"

# Configuration
MAX_PAGES_PER_SEARCH = 50  # Deep scan - 50 pages
ITEMS_PER_PAGE = 96  # Maximum items per page
PAGE_DELAY = 3  # Faster page delays
PRODUCT_DELAY = 8  # Shorter delay between products
CYCLE_INTERVAL = 600  # 10 minutes between cycles (more frequent)
MAX_PRODUCTS_PER_CYCLE = 2  # Only 2 products - scan both each time
RETRY_DELAY = 30
MAX_RETRIES = 2
SESSION_RESET_DELAY = 60
SCRAPE_DELAY = 2  # Faster scraping
MIN_SELLER_REVIEWS = 1  # Require at least 1 review (filter out 0 reviews)

# CRITICAL EXCLUSIONS - Always filter these (for TITLE filtering)
CRITICAL_EXCLUSIONS_TITLE = [
    'broken', 'damaged', 'faulty', 'not working', 'for parts', 'spares', 'repair',
    'cracked', 'water damage', 'dead', 'replica', 'fake', 'poor condition',
    'smashed',
    'case', 'case only', 'protective case', 'hard case', 'soft case', 'carrying case',
    'bag', 'bag only', 'carry bag', 'storage bag', 'travel bag', 'shoulder bag',
    'mount', 'mount only', 'mounting', 'bracket', 'holder', 'stand',
    'battery', 'battery only', 'batteries', 'charger', 'charger only', 'power adapter',
    'cable', 'cable only', 'usb cable', 'power cable', 'connector',
    'strap', 'neck strap', 'wrist strap',
    'manual', 'manual only', 'instructions', 'box', 'box only', 'empty box',
    'memory card', 'sd card', 'card only',
    'remote', 'remote control', 'remote only',
    'propeller', 'propellers', 'props', 'blades',
    'gimbal', 'gimbal only', 'stabilizer',
    'screen protector', 'protector', 'guard',
    'sticker', 'skin', 'decal', 'wrap',
    'dummy', 'display model', 'display only', 'non working display',
    # Other DJI models to exclude
    'mini 3', 'mini 4', 'mavic', 'air', 'phantom', 'inspire', 'fpv', 'avata',
    # Graphics cards & PC parts
    'rtx', 'gtx', 'graphics card', 'gpu', 'nvidia', 'amd', 'radeon',
    'air quality', 'dylos',
    'pc', 'computer', 'gaming', 'desktop',
    # Clothing & accessories
    'shoes', 'nike', 'adidas', 'clothing', 'shirt', 'jacket',
    # Audio devices
    'airpods', 'earbuds', 'headphones', 'beats',
    # Watches & fitness trackers
    'smart watch', 'smartwatch', 'apple watch', 'fitness tracker', 'fitness band',
    'mi band', 'whoop', 'fitbit', 'garmin watch', 'sports watch',
    # Phone accessories & random tech
    'phone holder', 'face tracker', 'smartphone', 'carplay', 'android auto',
    'wireless dongle', 'adapter', 'car', 'vehicle',
    # Toys & baby items  
    'troll', 'toy', 'baby', 'bouncer', 'crib', 'bed',
    # Sports equipment
    'football', 'soccer', 'playermaker', 'shoe sizes',
    # Car parts
    'vauxhall', 'insignia', 'pedal box', 'chip tuning',
    # Health & wellness
    'massage', 'massage gun', 'wellness',
    # Airsoft/gaming accessories
    'tracer unit', 'airsoft', 'ksg',
]

# DESCRIPTION EXCLUSIONS - Check after scraping description
CRITICAL_EXCLUSIONS_DESC = [
    'broken', 'damaged', 'faulty', 'not working', 'doesn\'t work', 'does not work',
    'for parts', 'spares', 'repair needed', 'needs repair', 'needs fixing',
    'cracked', 'crack', 'scratched badly', 'heavily scratched', 'major scratches',
    'water damage', 'water damaged', 'liquid damage', 'moisture damage',
    'dead', 'won\'t turn on', 'doesn\'t turn on', 'no power', 'will not power on',
    'replica', 'fake', 'copy', 'counterfeit', 'imitation', 'knock off', 'knockoff',
    'poor condition', 'very poor', 'terrible condition', 'unusable',
    'smashed', 'shattered',
    'locked', 'password protected', 'can\'t access', 'cannot access',
    'stolen', 'lost property', 'found',
    'fly away', 'flyaway', 'lost drone', 'crashed',
]

# GOOD INDICATORS in description (bonus points, but not required)
GOOD_INDICATORS = [
    'mint', 'perfect', 'pristine', 'excellent', 'like new', 'brand new',
    'barely used', 'hardly used', 'lightly used',
    'full working', 'fully working', 'perfect working', 'works perfectly',
    'original box', 'boxed', 'box included', 'with box',
    'warranty', 'receipt', 'proof of purchase',
    'charger included', 'battery included', 'batteries included', 'accessories included',
    'no scratches', 'scratch free', 'immaculate',
    'fly more combo', 'combo', 'extra batteries',
]

# Product specifications with buy prices - ONLY DJI MINI 2 MODELS
PRODUCT_SPECS = {
    # === DJI MINI 2 DRONES ONLY ===
    # Use simpler search terms - let filters handle the rest
    'dji mini 2': {
        'max_buy': 180.0, 
        'target_list': 350.0, 
        'min_profit': 120.0,
        'search_terms': ['dji mini 2']  # Simple, broad search
    },
    'dji mini 2 se': {
        'max_buy': 140.0, 
        'target_list': 280.0, 
        'min_profit': 100.0,
        'search_terms': ['dji mini 2 se']  # Simple, broad search
    },
}

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1422243737261707382/aoFqRx4rpIaplAGL96W8r19iCLrucHCt7gbdmK2hLzXP9q9QZO3pGJAi9OBqW1Ghunaz")

def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            search_term TEXT NOT NULL,
            price_from REAL NOT NULL,
            price_to REAL NOT NULL,
            target_list_price REAL NOT NULL,
            min_profit REAL NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            last_checked TEXT,
            total_found INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vinted_id TEXT UNIQUE NOT NULL,
            search_query_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            url TEXT NOT NULL,
            photo_url TEXT,
            description TEXT,
            seller_reviews INTEGER,
            passed_title_filter BOOLEAN DEFAULT FALSE,
            passed_desc_filter BOOLEAN DEFAULT FALSE,
            profit REAL,
            notified_at TEXT NOT NULL,
            FOREIGN KEY (search_query_id) REFERENCES search_queries(id)
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

async def create_search_queries():
    """Create search queries from PRODUCT_SPECS"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    for product_name, pricing in PRODUCT_SPECS.items():
        max_buy = pricing['max_buy']
        target_list = pricing['target_list']
        min_profit = pricing['min_profit']
        
        # Use the first search term as primary
        search_terms = pricing.get('search_terms', [product_name])
        primary_search_term = search_terms[0]
        
        # Price range: 5% below min profit point to max buy price
        min_price_threshold = max_buy - min_profit
        price_from = max(min_price_threshold * 0.95, 1.0)
        price_to = max_buy
        
        cursor.execute("""
            INSERT OR IGNORE INTO search_queries 
            (name, search_term, price_from, price_to, target_list_price, min_profit, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product_name,
            primary_search_term,
            price_from,
            price_to,
            target_list,
            min_profit,
            datetime.utcnow().isoformat()
        ))
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Created {len(PRODUCT_SPECS)} search queries")

def has_critical_exclusion_in_title(title: str) -> Tuple[bool, Optional[str]]:
    """Check if title contains critical exclusion terms"""
    title_lower = title.lower()
    for term in CRITICAL_EXCLUSIONS_TITLE:
        if term in title_lower:
            return True, term
    return False, None

def has_required_drone_keywords(title: str, product_name: str) -> bool:
    """Check if title contains required DJI Mini 2 keywords"""
    title_lower = title.lower()
    product_lower = product_name.lower()
    
    # Must have DJI
    if 'dji' not in title_lower:
        return False
    
    # Must have Mini or Mini 2
    if 'mini 2' not in title_lower and 'mini2' not in title_lower:
        if 'mini' not in title_lower:
            return False
    
    # If looking for SE specifically, check for SE
    if 'se' in product_lower:
        if 'se' not in title_lower:
            return False
    
    return True

def has_critical_exclusion_in_description(description: str) -> Tuple[bool, Optional[str]]:
    """Check if description contains critical exclusion terms"""
    if not description:
        return False, None
    
    desc_lower = description.lower()
    for term in CRITICAL_EXCLUSIONS_DESC:
        if term in desc_lower:
            return True, term
    return False, None

def calculate_quality_score(description: str) -> int:
    """Calculate quality score based on good indicators (0-100)"""
    if not description:
        return 50  # Neutral score if no description
    
    desc_lower = description.lower()
    score = 50  # Start at neutral
    
    for indicator in GOOD_INDICATORS:
        if indicator in desc_lower:
            score += 10  # Add 10 points per good indicator
    
    return min(score, 100)  # Cap at 100

async def scrape_vinted_description(url: str) -> Tuple[Optional[str], Optional[int]]:
    """Scrape full description and seller review count from Vinted listing page"""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            description = None
            review_count = None
            
            # Try multiple selectors for description
            description_selectors = [
                'div[itemprop="description"]',
                'div.details-list__item-value',
                'div.item-description',
                'p.item-description',
            ]
            
            for selector in description_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                    if description and len(description) > 10:
                        break
            
            # Try to extract seller review count
            review_selectors = [
                'span.user-feedback__rating-count',
                'div.user-feedback__rating-count',
                'span.feedback-reputation__rating',
                'div.feedback-reputation__rating',
            ]
            
            for selector in review_selectors:
                review_elem = soup.select_one(selector)
                if review_elem:
                    review_text = review_elem.get_text(strip=True)
                    # Extract number from text like "(123)" or "123 reviews"
                    review_match = re.search(r'(\d+)', review_text)
                    if review_match:
                        review_count = int(review_match.group(1))
                        break
            
            return description, review_count
            
    except Exception as e:
        logger.debug(f"      ⚠️  Scrape error: {e}")
        return None, None

async def send_discord_notification(item_data: dict):
    """Send notification to Discord"""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("⚠️  No Discord webhook configured")
        return
    
    try:
        profit = item_data['profit']
        profit_margin = (profit / item_data['target_list']) * 100
        
        # Color based on profit margin
        if profit_margin >= 40:
            color = 0x00ff00  # Green - Excellent
        elif profit_margin >= 25:
            color = 0xffa500  # Orange - Good
        else:
            color = 0xff6b6b  # Red - Acceptable
        
        quality_score = item_data.get('quality_score', 50)
        quality_emoji = "🌟" if quality_score >= 70 else "✅" if quality_score >= 50 else "⚠️"
        
        seller_reviews = item_data.get('seller_reviews')
        review_emoji = "⭐" if seller_reviews and seller_reviews >= 10 else "👤"
        review_text = f"{seller_reviews} reviews" if seller_reviews else "New seller"
        
        description_preview = item_data.get('description', 'No description available')
        if description_preview and len(description_preview) > 200:
            description_preview = description_preview[:200] + "..."
        
        embed = {
            "title": f"🚁 {item_data['product_name'].upper()}",
            "description": f"**{item_data['title']}**",
            "color": color,
            "fields": [
                {
                    "name": "💰 Buy Price",
                    "value": f"£{item_data['price']:.2f}",
                    "inline": True
                },
                {
                    "name": "🎯 Target List",
                    "value": f"£{item_data['target_list']:.2f}",
                    "inline": True
                },
                {
                    "name": "💵 Profit",
                    "value": f"£{profit:.2f} ({profit_margin:.1f}%)",
                    "inline": True
                },
                {
                    "name": f"{quality_emoji} Quality Score",
                    "value": f"{quality_score}/100",
                    "inline": True
                },
                {
                    "name": f"{review_emoji} Seller",
                    "value": review_text,
                    "inline": True
                },
                {
                    "name": "📝 Description",
                    "value": description_preview,
                    "inline": False
                }
            ],
            "url": item_data['url'],
            "thumbnail": {"url": item_data['photo_url']} if item_data.get('photo_url') else None,
            "footer": {
                "text": f"DJI Drones Bot • {datetime.utcnow().strftime('%H:%M:%S UTC')}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
            
            if response.status_code == 404:
                logger.error("❌ Discord webhook not found (404) - Please update DISCORD_WEBHOOK_URL")
            elif response.status_code != 204 and response.status_code != 200:
                logger.error(f"❌ Discord webhook error: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Discord notification error: {e}")

async def run_scan_cycle():
    """Run a complete scan cycle"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, search_term, price_from, price_to, target_list_price, min_profit
        FROM search_queries
        WHERE enabled = TRUE
        ORDER BY RANDOM()
        LIMIT ?
    """, (MAX_PRODUCTS_PER_CYCLE,))
    
    queries = cursor.fetchall()
    
    if not queries:
        logger.warning("⚠️  No enabled search queries found")
        conn.close()
        return
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🚁 STARTING SCAN CYCLE - DJI Drones Bot")
    logger.info(f"{'='*60}")
    logger.info(f"🕐 Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📦 Processing: {len(queries)} products")
    logger.info(f"")
    
    cycle_stats = {
        'total_items': 0,
        'already_tracked': 0,
        'passed_title_filter': 0,
        'descriptions_scraped': 0,
        'passed_desc_filter': 0,
        'sent_to_discord': 0,
        'filtered_title': 0,
        'filtered_desc': 0
    }
    
    try:
        scraper = AsyncVintedScraper(baseurl="https://www.vinted.co.uk")
        
        for idx, query in enumerate(queries, 1):
            query_id, name, search_term, price_from, price_to, target_list, min_profit = query
            
            logger.info(f"\n{'─'*60}")
            logger.info(f"🔍 [{idx}/{len(queries)}] {name}")
            logger.info(f"{'─'*60}")
            logger.info(f"   💷 Price range: £{price_from:.2f} - £{price_to:.2f}")
            logger.info(f"   🎯 Target list: £{target_list:.2f}")
            logger.info(f"   💰 Min profit: £{min_profit:.2f}")
            logger.info(f"")
            
            all_items = []
            
            # Paginate through results
            for page in range(1, MAX_PAGES_PER_SEARCH + 1):
                try:
                    logger.info(f"   📄 Fetching page {page}/{MAX_PAGES_PER_SEARCH}...")
                    
                    search_params = {
                        "search_text": search_term,
                        "price_from": price_from,
                        "price_to": price_to,
                        "per_page": ITEMS_PER_PAGE,
                        "page": page,
                        "catalog_ids": "1652",  # Electronics category
                        "order": "newest_first"  # Get newest listings first
                    }
                    
                    items = await scraper.search(params=search_params)
                    
                    if not items:
                        logger.info(f"      ℹ️  No more items on page {page}")
                        break
                    
                    all_items.extend(items)
                    logger.info(f"      ✅ Found {len(items)} items")
                    
                    if len(items) < ITEMS_PER_PAGE:
                        logger.info(f"      ℹ️  Last page reached ({len(items)} items)")
                        break
                    
                    if page < MAX_PAGES_PER_SEARCH:
                        await asyncio.sleep(PAGE_DELAY)
                        
                except Exception as e:
                    logger.error(f"      ❌ Page {page} error: {e}")
                    break
            
            cycle_stats['total_items'] += len(all_items)
            logger.info(f"   📊 Total items fetched: {len(all_items)}")
            logger.info(f"")
            
            # Process items
            product_already_tracked = 0
            product_passed = 0
            product_filtered = 0
            
            for item in all_items:
                try:
                    # Check if already tracked
                    cursor.execute("SELECT id FROM tracked_items WHERE vinted_id = ?", (str(item.id),))
                    if cursor.fetchone():
                        product_already_tracked += 1
                        continue
                    
                    logger.info(f"   🆕 New item #{item.id}: {item.title[:60]}...")
                    
                    # Step 1: Title filter - exclusions
                    has_exclusion, term = has_critical_exclusion_in_title(item.title)
                    if has_exclusion:
                        logger.info(f"      ❌ Title filter: '{term}'")
                        product_filtered += 1
                        cycle_stats['filtered_title'] += 1
                        continue
                    
                    # Step 1.5: Check for required drone keywords
                    if not has_required_drone_keywords(item.title, name):
                        logger.info(f"      ❌ Missing required DJI Mini 2 keywords")
                        product_filtered += 1
                        cycle_stats['filtered_title'] += 1
                        continue
                    
                    logger.info(f"      ✅ Title filter passed")
                    cycle_stats['passed_title_filter'] += 1
                    
                    # Step 2: Green light - scrape description
                    logger.info(f"      🔍 Scraping description & seller info...")
                    description, review_count = await scrape_vinted_description(item.url)
                    cycle_stats['descriptions_scraped'] += 1
                    
                    if description:
                        logger.info(f"      ✅ Description: {description[:80]}...")
                    else:
                        logger.info(f"      ⚠️  No description found")
                    
                    if review_count is not None:
                        logger.info(f"      ⭐ Seller reviews: {review_count}")
                    else:
                        logger.info(f"      ⚠️  Could not fetch seller reviews")
                    
                    # Step 2.5: Filter out sellers with 0 reviews
                    if review_count is not None and review_count < MIN_SELLER_REVIEWS:
                        logger.info(f"      ❌ Seller has {review_count} reviews (minimum: {MIN_SELLER_REVIEWS})")
                        cycle_stats['filtered_desc'] += 1
                        product_filtered += 1
                        continue
                    
                    # Step 3: Description filter
                    if description:
                        has_exclusion, term = has_critical_exclusion_in_description(description)
                        if has_exclusion:
                            logger.info(f"      ❌ Description filter: '{term}'")
                            cycle_stats['filtered_desc'] += 1
                            product_filtered += 1
                            continue
                    
                    logger.info(f"      ✅ Description filter passed")
                    cycle_stats['passed_desc_filter'] += 1
                    
                    # Step 4: Calculate quality score
                    quality_score = calculate_quality_score(description)
                    logger.info(f"      ⭐ Quality score: {quality_score}/100")
                    
                    # Calculate profit
                    profit = target_list - item.price
                    
                    # Extract photo URL properly
                    photo_url = None
                    if hasattr(item, 'photo'):
                        if isinstance(item.photo, dict):
                            photo_url = item.photo.get('url') or item.photo.get('full_size_url')
                        elif isinstance(item.photo, str):
                            photo_url = item.photo
                    
                    # Save to database
                    cursor.execute("""
                        INSERT INTO tracked_items 
                        (vinted_id, search_query_id, title, price, url, photo_url, description,
                         seller_reviews, passed_title_filter, passed_desc_filter, profit, notified_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(item.id),
                        query_id,
                        item.title,
                        item.price,
                        item.url,
                        photo_url,
                        description,
                        review_count,
                        True,
                        True,
                        profit,
                        datetime.utcnow().isoformat()
                    ))
                    
                    cursor.execute("UPDATE search_queries SET total_found = total_found + 1 WHERE id = ?",
                                 (query_id,))
                    
                    product_passed += 1
                    cycle_stats['sent_to_discord'] += 1
                    
                    logger.info(f"      💰 Profit: £{profit:.2f}")
                    logger.info(f"      📬 Sending to Discord...")
                    
                    # Extract photo URL for Discord
                    photo_url_discord = None
                    if hasattr(item, 'photo'):
                        if isinstance(item.photo, dict):
                            photo_url_discord = item.photo.get('url') or item.photo.get('full_size_url')
                        elif isinstance(item.photo, str):
                            photo_url_discord = item.photo
                    
                    # Send to Discord
                    await send_discord_notification({
                        'product_name': name,
                        'title': item.title,
                        'price': item.price,
                        'target_list': target_list,
                        'profit': profit,
                        'url': item.url,
                        'photo_url': photo_url_discord,
                        'description': description,
                        'quality_score': quality_score,
                        'seller_reviews': review_count
                    })
                    
                    logger.info(f"      ✅ Notification sent!")
                    logger.info("")
                    
                    # Delay between items
                    if product_passed < len(all_items):
                        await asyncio.sleep(SCRAPE_DELAY)
                    
                except Exception as e:
                    logger.error(f"      ❌ Error processing item #{item.id}: {e}")
                    continue
            
            logger.info(f"\n{'─'*60}")
            logger.info(f"📊 {name} - Summary:")
            logger.info(f"   📦 Total scanned: {len(all_items)}")
            logger.info(f"   ⭐ Already tracked: {product_already_tracked}")
            logger.info(f"   ✅ Passed filters: {product_passed}")
            logger.info(f"   ❌ Filtered out: {product_filtered}")
            logger.info(f"   📬 Sent to Discord: {product_passed}")
            logger.info(f"{'─'*60}")
            
            cursor.execute("UPDATE search_queries SET last_checked = ? WHERE id = ?",
                         (datetime.utcnow().isoformat(), query_id))
            
            if idx < len(queries):
                logger.info(f"\n💤 Waiting {PRODUCT_DELAY}s before next product...")
                await asyncio.sleep(PRODUCT_DELAY)
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    finally:
        logger.info(f"\n💾 Committing database changes...")
        conn.commit()
        conn.close()
        logger.info(f"✅ Database updated")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 CYCLE COMPLETE - DJI Drones Bot")
        logger.info(f"{'='*60}")
        logger.info(f"🕐 Completed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f"")
        logger.info(f"📈 Cycle Statistics:")
        logger.info(f"   📦 Total items scanned: {cycle_stats['total_items']:,}")
        logger.info(f"   ⭐ Already tracked: {cycle_stats['already_tracked']}")
        logger.info(f"   ✅ Passed title filters: {cycle_stats['passed_title_filter']}")
        logger.info(f"   📝 Descriptions scraped: {cycle_stats['descriptions_scraped']}")
        logger.info(f"   ✅ Passed description filters: {cycle_stats['passed_desc_filter']}")
        logger.info(f"   📬 Sent to Discord: {cycle_stats['sent_to_discord']}")
        logger.info(f"   ❌ Filtered by title: {cycle_stats['filtered_title']}")
        logger.info(f"   ❌ Filtered by description: {cycle_stats['filtered_desc']}")
        logger.info(f"{'='*60}")
        logger.info(f"\n⏰ Next cycle in {CYCLE_INTERVAL//60} minutes...\n")

async def scheduler():
    """Background scheduler for scan cycles"""
    await asyncio.sleep(5)
    
    while True:
        try:
            await run_scan_cycle()
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info(f"💤 Waiting {CYCLE_INTERVAL}s before next cycle...\n")
        await asyncio.sleep(CYCLE_INTERVAL)

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("\n" + "="*60)
    logger.info("🚁 DJI DRONES BOT STARTING")
    logger.info("="*60)
    
    if not VINTED_AVAILABLE:
        logger.warning("⚠️ WARNING: vinted_scraper not installed!")
        logger.warning("⚠️ Install with: pip install vinted-scraper")
    
    init_database()
    await create_search_queries()
    
    logger.info(f"\n⚙️  DJI DRONES BOT CONFIGURATION:")
    logger.info(f"   🚁 Specialty: DJI Mini 2 & Mini 2 SE Only")
    logger.info(f"   🎯 Products tracked: {len(PRODUCT_SPECS)}")
    logger.info(f"   🔍 Pages per product: {MAX_PAGES_PER_SEARCH} (DEEP SCAN)")
    logger.info(f"   📦 Max items per product: ~{MAX_PAGES_PER_SEARCH * ITEMS_PER_PAGE:,}")
    logger.info(f"   🔄 Products per cycle: {MAX_PRODUCTS_PER_CYCLE} (ALL)")
    logger.info(f"   ⏱️  Cycle time: {CYCLE_INTERVAL//60} minutes (FREQUENT)")
    logger.info(f"   💰 DJI Mini 2 max buy: £180")
    logger.info(f"   💰 DJI Mini 2 SE max buy: £140")
    logger.info(f"   ⭐ Min seller reviews: {MIN_SELLER_REVIEWS}")
    logger.info(f"   🔍 Description scraping: ✅ ENABLED")
    logger.info(f"   ⭐ Quality scoring: ✅ ENABLED")
    logger.info(f"   🔌 Vinted scraper: {'✅ AVAILABLE' if VINTED_AVAILABLE else '❌ NOT INSTALLED'}")
    logger.info(f"="*60 + "\n")
    
    # Start scheduler
    asyncio.create_task(scheduler())

@app.get("/", response_class=HTMLResponse)
async def home():
    """Bot dashboard"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM tracked_items")
    total_items = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tracked_items WHERE passed_title_filter = TRUE")
    passed_title = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tracked_items WHERE passed_desc_filter = TRUE")
    passed_desc = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(profit) FROM tracked_items")
    total_profit = cursor.fetchone()[0] or 0
    
    cursor.execute("""
        SELECT name, COUNT(tracked_items.id) as count
        FROM search_queries
        LEFT JOIN tracked_items ON search_queries.id = tracked_items.search_query_id
        WHERE search_queries.enabled = TRUE
        GROUP BY search_queries.id
        ORDER BY count DESC
        LIMIT 10
    """)
    top_products = cursor.fetchall()
    
    cursor.execute("""
        SELECT title, price, url, profit, notified_at
        FROM tracked_items
        ORDER BY notified_at DESC
        LIMIT 20
    """)
    recent_items = cursor.fetchall()
    
    conn.close()
    
    html = f"""
    <html>
        <head>
            <title>DJI Drones Bot Dashboard</title>
            <meta http-equiv="refresh" content="60">
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    min-height: 100vh; 
                    padding: 20px; 
                    margin: 0;
                }}
                .container {{ 
                    max-width: 1200px; 
                    margin: 0 auto; 
                    background: white; 
                    padding: 40px; 
                    border-radius: 20px; 
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3); 
                }}
                h1 {{ 
                    color: #333; 
                    font-size: 42px; 
                    margin-bottom: 10px; 
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }}
                .subtitle {{ 
                    color: #666; 
                    font-size: 18px; 
                    margin-bottom: 30px; 
                }}
                .stats {{ 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                    gap: 20px; 
                    margin: 30px 0; 
                }}
                .stat {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 25px; 
                    border-radius: 15px; 
                    color: white; 
                    box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                }}
                .stat-value {{ 
                    font-size: 36px; 
                    font-weight: bold; 
                    margin: 10px 0; 
                }}
                .stat-label {{ 
                    font-size: 14px; 
                    opacity: 0.9; 
                }}
                .section {{ 
                    margin: 30px 0; 
                    background: #f8f9fa; 
                    padding: 25px; 
                    border-radius: 15px; 
                }}
                .section h2 {{ 
                    color: #333; 
                    margin-top: 0; 
                    font-size: 24px;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }}
                table {{ 
                    width: 100%; 
                    border-collapse: collapse; 
                    margin-top: 15px; 
                }}
                th {{ 
                    background: #667eea; 
                    color: white; 
                    padding: 12px; 
                    text-align: left; 
                    font-weight: 600;
                }}
                td {{ 
                    padding: 12px; 
                    border-bottom: 1px solid #ddd; 
                }}
                tr:hover {{ 
                    background: #f0f0f0; 
                }}
                .deal-item {{ 
                    background: white; 
                    padding: 15px; 
                    margin: 10px 0; 
                    border-radius: 10px; 
                    border-left: 4px solid #667eea;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .deal-title {{ 
                    font-weight: bold; 
                    color: #333; 
                    margin-bottom: 8px;
                }}
                .deal-info {{ 
                    color: #666; 
                    font-size: 14px;
                    display: flex;
                    gap: 20px;
                    flex-wrap: wrap;
                }}
                .profit-positive {{ 
                    color: #00a86b; 
                    font-weight: bold; 
                }}
                a {{ 
                    color: #667eea; 
                    text-decoration: none; 
                }}
                a:hover {{ 
                    text-decoration: underline; 
                }}
                .status {{ 
                    display: inline-block; 
                    padding: 4px 12px; 
                    background: #00a86b; 
                    color: white; 
                    border-radius: 12px; 
                    font-size: 12px; 
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>
                    <span>🚁</span> DJI Drones Bot
                </h1>
                <div class="subtitle">
                    <span class="status">● LIVE</span>
                    Tracking DJI Mini 2 & Mini 2 SE • Deep scan: 50 pages • Cycle: 10 min • Min reviews: 1 • Auto-refresh: 60s
                </div>
                
                <div class="stats">
                    <div class="stat">
                        <div class="stat-label">💎 Total Deals Found</div>
                        <div class="stat-value">{total_items}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">✅ Title Filter Pass</div>
                        <div class="stat-value">{passed_title}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">📝 Description Pass</div>
                        <div class="stat-value">{passed_desc}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">💰 Total Profit Potential</div>
                        <div class="stat-value">£{total_profit:,.0f}</div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>🏆 Top Products</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Product</th>
                                <th>Deals Found</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(f'<tr><td>{name}</td><td>{count}</td></tr>' for name, count in top_products)}
                        </tbody>
                    </table>
                </div>
                
                <div class="section">
                    <h2>🔥 Recent Deals (Last 20)</h2>
                    <div>
                        {''.join(f'''
                            <div class="deal-item">
                                <div class="deal-title">{title}</div>
                                <div class="deal-info">
                                    <span>💰 £{price:.2f}</span>
                                    <span class="profit-positive">📈 +£{profit:.2f} profit</span>
                                    <span>🕐 {notified_at.split('T')[1][:8]}</span>
                                    <span><a href="{url}" target="_blank">🔗 View Listing</a></span>
                                </div>
                            </div>
                        ''' for title, price, url, profit, notified_at in recent_items) if recent_items else '<p style="padding: 20px; text-align: center; color: #999;">No deals yet...</p>'}
                    </div>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "bot": "dji_drones",
        "products_tracked": len(PRODUCT_SPECS),
        "scan_interval": CYCLE_INTERVAL,
        "description_scraping": True,
        "quality_scoring": True,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
