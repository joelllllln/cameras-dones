#!/usr/bin/env python3
"""
BOT 3: Camera & DJ Pro - Complete Production Version
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

try:
    from vinted_scraper import AsyncVintedScraper
except ImportError:
    print("Warning: vinted_scraper not installed")
    class AsyncVintedScraper:
        def __init__(self, baseurl):
            self.baseurl = baseurl
        async def search(self, params):
            return []

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Camera & DJ Pro Bot")
DATABASE_FILE = "camera_dj_bot.db"

# Configuration
MAX_PAGES_PER_SEARCH = 20
ITEMS_PER_PAGE = 40
PAGE_DELAY = 4
PRODUCT_DELAY = 12
CYCLE_INTERVAL = 900
MAX_PRODUCTS_PER_CYCLE = 8
RETRY_DELAY = 30
MAX_RETRIES = 2
SESSION_RESET_DELAY = 60
SCRAPE_DELAY = 3

# CRITICAL EXCLUSIONS - Always filter these (for TITLE filtering)
CRITICAL_EXCLUSIONS_TITLE = [
    'broken', 'damaged', 'faulty', 'not working', 'for parts', 'spares', 'repair',
    'cracked', 'water damage', 'dead', 'replica', 'fake', 'poor condition',
    'smashed',
    'case', 'case only', 'protective case', 'hard case', 'soft case', 'carrying case',
    'bag', 'bag only', 'carry bag', 'storage bag', 'travel bag', 'shoulder bag',
    'mount', 'mount only', 'mounting', 'bracket', 'holder', 'stand',
    'battery', 'battery only', 'batteries', 'charger', 'charger only', 'power adapter',
    'lens', 'lens only', 'replacement lens', 'lens cover', 'lens cap',
    'cable', 'cable only', 'usb cable', 'power cable', 'connector',
    'strap', 'neck strap', 'wrist strap', 'camera strap',
    'manual', 'manual only', 'instructions', 'box', 'box only', 'empty box',
    'memory card', 'sd card', 'cf card', 'card only',
    'remote', 'remote control', 'remote only',
    'tripod', 'monopod', 'gimbal', 'stabilizer',
    'filter', 'uv filter', 'nd filter', 'polarizing filter',
    'flash', 'external flash', 'speedlight', 'flash unit',
    'screen protector', 'protector', 'guard',
    'sticker', 'skin', 'decal', 'wrap',
    'dummy', 'display model', 'display only', 'non working display',
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
]

# GOOD INDICATORS in description (bonus points, but not required)
GOOD_INDICATORS = [
    'mint', 'perfect', 'pristine', 'excellent', 'like new', 'brand new',
    'barely used', 'hardly used', 'lightly used',
    'full working', 'fully working', 'perfect working', 'works perfectly',
    'original box', 'boxed', 'box included', 'with box',
    'warranty', 'receipt', 'proof of purchase',
    'charger included', 'battery included', 'accessories included',
    'no scratches', 'scratch free', 'immaculate',
]

# Product specifications with buy prices
PRODUCT_SPECS = {
    # === CAMERAS ===
    # Canon
    'canon eos r5': {'max_buy': 1400.0, 'target_list': 2200.0, 'min_profit': 600.0},
    'canon eos r6': {'max_buy': 900.0, 'target_list': 1500.0, 'min_profit': 450.0},
    'canon eos r': {'max_buy': 600.0, 'target_list': 1000.0, 'min_profit': 300.0},
    'canon eos 5d mark iv': {'max_buy': 700.0, 'target_list': 1200.0, 'min_profit': 350.0},
    'canon eos 6d mark ii': {'max_buy': 450.0, 'target_list': 800.0, 'min_profit': 250.0},
    'canon eos 90d': {'max_buy': 500.0, 'target_list': 850.0, 'min_profit': 250.0},
    'canon eos m50': {'max_buy': 200.0, 'target_list': 400.0, 'min_profit': 150.0},
    
    # Sony
    'sony a7iii': {'max_buy': 800.0, 'target_list': 1300.0, 'min_profit': 400.0},
    'sony a7 iii': {'max_buy': 800.0, 'target_list': 1300.0, 'min_profit': 400.0},
    'sony a7iv': {'max_buy': 1200.0, 'target_list': 1900.0, 'min_profit': 500.0},
    'sony a7 iv': {'max_buy': 1200.0, 'target_list': 1900.0, 'min_profit': 500.0},
    'sony a7siii': {'max_buy': 1600.0, 'target_list': 2500.0, 'min_profit': 650.0},
    'sony a7s iii': {'max_buy': 1600.0, 'target_list': 2500.0, 'min_profit': 650.0},
    'sony a7riv': {'max_buy': 1400.0, 'target_list': 2200.0, 'min_profit': 600.0},
    'sony a7r iv': {'max_buy': 1400.0, 'target_list': 2200.0, 'min_profit': 600.0},
    'sony a6400': {'max_buy': 400.0, 'target_list': 700.0, 'min_profit': 220.0},
    'sony a6600': {'max_buy': 550.0, 'target_list': 950.0, 'min_profit': 300.0},
    'sony zv-e10': {'max_buy': 350.0, 'target_list': 600.0, 'min_profit': 180.0},
    'sony zv-1': {'max_buy': 300.0, 'target_list': 550.0, 'min_profit': 180.0},
    
    # Nikon
    'nikon z6': {'max_buy': 650.0, 'target_list': 1100.0, 'min_profit': 330.0},
    'nikon z6 ii': {'max_buy': 850.0, 'target_list': 1400.0, 'min_profit': 400.0},
    'nikon z7': {'max_buy': 850.0, 'target_list': 1400.0, 'min_profit': 400.0},
    'nikon z7 ii': {'max_buy': 1100.0, 'target_list': 1800.0, 'min_profit': 500.0},
    'nikon d850': {'max_buy': 950.0, 'target_list': 1600.0, 'min_profit': 480.0},
    'nikon d750': {'max_buy': 400.0, 'target_list': 700.0, 'min_profit': 220.0},
    
    # Fujifilm
    'fujifilm xt4': {'max_buy': 700.0, 'target_list': 1150.0, 'min_profit': 340.0},
    'fujifilm x-t4': {'max_buy': 700.0, 'target_list': 1150.0, 'min_profit': 340.0},
    'fujifilm xt3': {'max_buy': 450.0, 'target_list': 800.0, 'min_profit': 250.0},
    'fujifilm x-t3': {'max_buy': 450.0, 'target_list': 800.0, 'min_profit': 250.0},
    'fujifilm xs10': {'max_buy': 400.0, 'target_list': 700.0, 'min_profit': 220.0},
    'fujifilm x-s10': {'max_buy': 400.0, 'target_list': 700.0, 'min_profit': 220.0},
    
    # GoPro
    'gopro hero 11': {'max_buy': 180.0, 'target_list': 320.0, 'min_profit': 100.0},
    'gopro hero 10': {'max_buy': 140.0, 'target_list': 260.0, 'min_profit': 85.0},
    'gopro hero 9': {'max_buy': 100.0, 'target_list': 200.0, 'min_profit': 70.0},
    
    # DJI Cameras/Gimbals
    'dji osmo pocket': {'max_buy': 100.0, 'target_list': 200.0, 'min_profit': 70.0},
    'dji osmo pocket 2': {'max_buy': 140.0, 'target_list': 260.0, 'min_profit': 85.0},
    'dji pocket 2': {'max_buy': 140.0, 'target_list': 260.0, 'min_profit': 85.0},
    'dji ronin': {'max_buy': 200.0, 'target_list': 400.0, 'min_profit': 140.0},
    
    # === DRONES ===
    'dji mini 3 pro': {'max_buy': 300.0, 'target_list': 550.0, 'min_profit': 180.0},
    'dji mini 3': {'max_buy': 220.0, 'target_list': 420.0, 'min_profit': 140.0},
    'dji mini 2': {'max_buy': 150.0, 'target_list': 300.0, 'min_profit': 105.0},
    'dji mavic 3': {'max_buy': 800.0, 'target_list': 1350.0, 'min_profit': 400.0},
    'dji mavic 3 pro': {'max_buy': 1000.0, 'target_list': 1700.0, 'min_profit': 500.0},
    'dji mavic 2 pro': {'max_buy': 400.0, 'target_list': 700.0, 'min_profit': 220.0},
    'dji mavic 2 zoom': {'max_buy': 350.0, 'target_list': 600.0, 'min_profit': 180.0},
    'dji mavic air 2': {'max_buy': 250.0, 'target_list': 450.0, 'min_profit': 150.0},
    'dji mavic air 2s': {'max_buy': 350.0, 'target_list': 600.0, 'min_profit': 180.0},
    'dji air 2s': {'max_buy': 350.0, 'target_list': 600.0, 'min_profit': 180.0},
    'dji fpv': {'max_buy': 300.0, 'target_list': 550.0, 'min_profit': 180.0},
    'dji avata': {'max_buy': 250.0, 'target_list': 450.0, 'min_profit': 150.0},
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
            product_name,
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

def has_required_camera_keywords(title: str, product_name: str) -> bool:
    """Check if title contains required camera/drone brand keywords"""
    title_lower = title.lower()
    product_lower = product_name.lower()
    
    # Extract brand from product name
    camera_brands = ['canon', 'sony', 'nikon', 'fujifilm', 'gopro', 'dji']
    
    # Check if any camera brand is in the title
    for brand in camera_brands:
        if brand in product_lower and brand in title_lower:
            return True
    
    # For DJI products, be extra strict
    if 'dji' in product_lower:
        if 'dji' not in title_lower and 'mavic' not in title_lower and 'mini' not in title_lower:
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
            "title": f"📸 {item_data['product_name'].upper()}",
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
                "text": f"Camera & DJ Bot • {datetime.utcnow().strftime('%H:%M:%S UTC')}"
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
    logger.info(f"🚀 STARTING SCAN CYCLE - Camera & DJ Bot")
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
                        "page": page
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
                        continue
                    
                    # Step 1.5: Check for required brand keywords
                    if not has_required_camera_keywords(item.title, name):
                        logger.info(f"      ❌ Missing brand keyword")
                        product_filtered += 1
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
        logger.info(f"📊 CYCLE COMPLETE - Camera & DJ Bot")
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
    logger.info("📸 CAMERA & DJ BOT STARTING")
    logger.info("="*60)
    
    init_database()
    await create_search_queries()
    
    logger.info(f"\n⚙️  BOT 3 CONFIGURATION:")
    logger.info(f"   📸 Specialty: Cameras & Drones")
    logger.info(f"   🎯 Products tracked: {len(PRODUCT_SPECS)}")
    logger.info(f"   🔍 Pages per product: {MAX_PAGES_PER_SEARCH}")
    logger.info(f"   📦 Items per product: ~{MAX_PAGES_PER_SEARCH * ITEMS_PER_PAGE}")
    logger.info(f"   🔄 Products per cycle: {MAX_PRODUCTS_PER_CYCLE}")
    logger.info(f"   ⏱️  Cycle time: {CYCLE_INTERVAL//60} minutes")
    logger.info(f"   🎯 Full rotation: ~{(len(PRODUCT_SPECS) // MAX_PRODUCTS_PER_CYCLE) * (CYCLE_INTERVAL//60)} minutes")
    logger.info(f"   🔍 Description scraping: ✅ ENABLED")
    logger.info(f"   ⭐ Quality scoring: ✅ ENABLED")
    logger.info(f"="*60 + "\n")
    
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
            <title>Camera & DJ Bot Dashboard</title>
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
                    <span>📸</span> Camera & DJ Bot
                </h1>
                <div class="subtitle">
                    <span class="status">● LIVE</span>
                    Tracking {len(PRODUCT_SPECS)} premium cameras and drones • Auto-refresh every 60s
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
        "bot": "camera_dj_pro",
        "products_tracked": len(PRODUCT_SPECS),
        "scan_interval": CYCLE_INTERVAL,
        "description_scraping": True,
        "quality_scoring": True,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
