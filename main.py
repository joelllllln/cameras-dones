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
        def __init__(self, base_url):
            self.base_url = base_url
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
    'battery', 'battery only', 'batteries', 'charger', 'charger only',
    'cable', 'cable only', 'usb cable', 'lead',
    'replacement', 'spare part', 'spare parts', 'component',
    'housing', 'frame', 'chassis', 'shell', 'body only',
    'lens', 'lens only', 'lens cap', 'filter', 'filter only',
    'remote', 'remote only', 'controller only', 'transmitter only',
    'propeller', 'propellers', 'props', 'blades', 'blade',
    'gimbal', 'gimbal only', 'stabilizer only',
    'screen protector', 'protector', 'guard',
    'box', 'empty box', 'just box', 'box only', 'packaging',
    'manual', 'instructions', 'guide only', 'papers',
    'accessories only', 'accessory', 'add on', 'addon'
]

# CRITICAL EXCLUSIONS for DESCRIPTIONS - Only truly bad conditions
CRITICAL_EXCLUSIONS_DESCRIPTION = [
    'broken', 'damaged', 'faulty', 'not working', 'doesnt work', "doesn't work",
    'for parts', 'spares', 'needs repair', 'requires repair',
    'water damage', 'water damaged', 'dead', 'wont turn on', "won't turn on",
    'poor condition', 'bad condition', 'replica', 'fake', 'imitation', 'copy',
    'spares or repair', 'spares or repairs', 'parts only', 'for spares',
    'smashed', 'smashed screen', 'screen smashed', 'cracked screen',
    'screen broken', 'broken screen', 'display broken', 'display cracked',
    'no power', 'wont power on', 'does not power on', 'power issue',
    'battery dead', 'battery faulty', 'battery issue', 'wont charge',
    'motor broken', 'motor issue', 'motor not working', 'motor faulty',
    'gimbal broken', 'gimbal issue', 'gimbal not working', 'gimbal faulty',
    'camera broken', 'camera issue', 'camera not working', 'camera faulty',
    'sensor broken', 'sensor issue', 'sensor not working', 'sensor faulty',
    'fly away', 'lost connection', 'connection lost', 'signal lost',
    'crashed', 'crash damage', 'impact damage', 'dropped',
    'missing parts', 'parts missing', 'incomplete', 'untested',
    'red light', 'error light', 'flashing red', 'warning light',
    'firmware issue', 'software issue', 'update failed', 'bricked',
]

PRODUCT_SPECS = {
    # GoPro Cameras - ALL possible variations
    'gopro hero 12': {
        'keywords': ['hero 12', 'hero12', '12 black', 'gopro 12', '12 gopro', 'hero 12 black', '12 hero', 'go pro 12'],
        'exclude': ['hero 11', 'hero 10', 'hero 9', 'hero 8', 'hero 7', '11', '10 ', '9 ', '8 ', '7 ', 'case', 'mount', 'battery', 'accessory'],
        'must_contain': ['12']
    },
    'gopro hero 11': {
        'keywords': ['hero 11', 'hero11', '11 black', 'gopro 11', '11 gopro', 'hero 11 black', '11 hero', 'go pro 11'],
        'exclude': ['hero 12', 'hero 10', 'hero 9', 'hero 8', 'hero 7', '12', '10 ', '9 ', '8 ', '7 ', 'case', 'mount', 'battery', 'accessory'],
        'must_contain': ['11']
    },
    'gopro hero 10': {
        'keywords': ['hero 10', 'hero10', '10 black', 'gopro 10', '10 gopro', 'hero 10 black', '10 hero', 'go pro 10'],
        'exclude': ['hero 12', 'hero 11', 'hero 9', 'hero 8', 'hero 7', '12', '11', '9 ', '8 ', '7 ', 'case', 'mount', 'battery', 'accessory'],
        'must_contain': ['10']
    },
    'gopro hero 9': {
        'keywords': ['hero 9', 'hero9', '9 black', 'gopro 9', '9 gopro', 'hero 9 black', '9 hero', 'go pro 9'],
        'exclude': ['hero 12', 'hero 11', 'hero 10', 'hero 8', 'hero 7', '12', '11', '10 ', '8 ', '7 ', 'case', 'mount', 'battery', 'accessory'],
        'must_contain': ['9']
    },
    'gopro hero 8': {
        'keywords': ['hero 8', 'hero8', '8 black', 'gopro 8', '8 gopro', 'hero 8 black', '8 hero', 'go pro 8'],
        'exclude': ['hero 12', 'hero 11', 'hero 10', 'hero 9', 'hero 7', '12', '11', '10 ', '9 ', '7 ', 'case', 'mount', 'battery', 'accessory'],
        'must_contain': ['8']
    },
    
    # DJI Drones - ALL possible variations
    'dji mavic 2 pro': {
        'keywords': ['mavic 2 pro', 'mavic2 pro', 'mavic 2pro', '2 pro drone', 'dji 2 pro', 'mavic pro 2', 'mavic2pro'],
        'exclude': ['mini', 'air ', 'case', 'bag', 'mavic 3', 'mavic pro platinum', 'battery', 'propeller', 'mavic air'],
        'must_contain': ['mavic', '2', 'pro']
    },
    'dji air 2s': {
        'keywords': ['air 2s', 'air2s', 'air 2 s', 'dji 2s', '2s drone', 'air2 s', 'mavic air 2s'],
        'exclude': ['mini', 'mavic air 2', 'case', 'bag', 'air 3', 'battery', 'propeller', 'air 2 '],
        'must_contain': ['air', '2s']
    },
    'dji mini 3 pro': {
        'keywords': ['mini 3 pro', 'mini3 pro', 'mini 3pro', 'mini3pro', 'dji mini 3', '3 pro drone', 'mini pro 3'],
        'exclude': ['mini 2', 'mini 4', 'case', 'bag', 'mini se', 'battery', 'propeller', 'mini 3 '],
        'must_contain': ['mini', '3', 'pro']
    },
    'dji mavic air 2': {
        'keywords': ['mavic air 2', 'mavic air2', 'air 2 drone', 'mavic 2 air', 'dji air 2', 'mavicair2', 'mavic air 2 '],
        'exclude': ['mini', 'case', 'bag', 'air 2s', 'mavic 3', 'battery', 'propeller', '2s'],
        'must_contain': ['mavic', 'air', '2']
    },
    'dji mini 2': {
        'keywords': ['mini 2', 'mini2', 'dji mini 2', 'mini 2 drone', 'mini2 drone', 'dji 2 mini'],
        'exclude': ['mini 3', 'mini 4', 'case', 'bag', 'mini se', 'mini pro', 'battery', 'propeller', '3 pro'],
        'must_contain': ['mini', '2']
    },
    
    # DJ Controllers - ALL possible variations
    'pioneer ddj-flx10': {
        'keywords': ['ddj-flx10', 'ddj flx10', 'flx10', 'flx 10', 'ddj flx 10', 'pioneer flx10', 'ddj-flx-10', 'ddjflx10'],
        'exclude': ['case', 'bag', 'cover', 'flx6', 'flx4', 'flx 6', 'flx 4', 'stand'],
        'must_contain': ['flx', '10']
    },
    'pioneer ddj-1000': {
        'keywords': ['ddj-1000', 'ddj 1000', 'ddj1000', 'pioneer 1000', 'ddj-1000srt', 'ddj 1000 srt', '1000 controller'],
        'exclude': ['ddj-800', 'ddj-400', 'case', 'bag', 'ddj-sx', 'ddj-sz', 'stand', '800', '400'],
        'must_contain': ['ddj', '1000']
    },
    'pioneer ddj-sx3': {
        'keywords': ['ddj-sx3', 'ddj sx3', 'sx3', 'ddj sx 3', 'ddjsx3', 'pioneer sx3', 'ddj-sx-3', 'sx 3 controller'],
        'exclude': ['ddj-sb3', 'case', 'bag', 'sx2', 'sx ', 'stand', 'sb3', 'sb 3'],
        'must_contain': ['sx', '3']
    },
    'pioneer ddj-800': {
        'keywords': ['ddj-800', 'ddj 800', 'ddj800', 'pioneer 800', 'ddj-800 controller', '800 controller', 'ddj 800 '],
        'exclude': ['ddj-1000', 'ddj-400', 'case', 'bag', 'ddj-sx', 'stand', '1000', '400'],
        'must_contain': ['ddj', '800']
    },
    'pioneer ddj-400': {
        'keywords': ['ddj-400', 'ddj 400', 'ddj400', 'pioneer 400', 'ddj-400 controller', '400 controller', 'ddj 400 '],
        'exclude': ['ddj-800', 'ddj-1000', 'case', 'bag', 'ddj-200', 'stand', '800', '1000', '200'],
        'must_contain': ['ddj', '400']
    },
    'pioneer ddj-sb3': {
        'keywords': ['ddj-sb3', 'ddj sb3', 'sb3', 'ddj sb 3', 'ddjsb3', 'pioneer sb3', 'ddj-sb-3', 'sb 3 controller'],
        'exclude': ['ddj-sx3', 'case', 'bag', 'sb2', 'sb ', 'stand', 'sx3', 'sx 3'],
        'must_contain': ['sb', '3']
    },
    'traktor s4': {
        'keywords': ['traktor s4', 'kontrol s4', 's4 mk3', 's4 mk2', 'traktor kontrol s4', 'ni s4', 's4 controller', 's4 mk 3', 's4 mk 2'],
        'exclude': ['case', 'bag', 's2', 's3', 's8', 'stand', 's 2', 's 3', 's 8'],
        'must_contain': ['s4']
    },
}

# Max buy prices - adjusted for realistic profit margins with -10% reduction
PRICING_DATA = {
    'gopro hero 12': {'max_buy': 300.0, 'min_buy': 59.6, 'target': 149.0, 'resell': 360.0, 'min_profit': 100.0},  # Increased for testing
    'gopro hero 11': {'max_buy': 250.0, 'min_buy': 46.4, 'target': 116.0, 'resell': 290.0, 'min_profit': 80.0},  # Increased for testing
    'gopro hero 10': {'max_buy': 200.0, 'min_buy': 36.0, 'target': 90.0, 'resell': 235.0, 'min_profit': 70.0},  # Increased for testing
    'gopro hero 9': {'max_buy': 150.0, 'min_buy': 26.4, 'target': 66.0, 'resell': 175.0, 'min_profit': 60.0},  # Increased for testing
    'gopro hero 8': {'max_buy': 120.0, 'min_buy': 19.2, 'target': 48.0, 'resell': 135.0, 'min_profit': 50.0},  # Increased for testing
    'dji mavic 2 pro': {'max_buy': 600.0, 'min_buy': 134.4, 'target': 336.0, 'resell': 820.0, 'min_profit': 250.0},  # Increased for testing
    'dji air 2s': {'max_buy': 500.0, 'min_buy': 103.6, 'target': 259.0, 'resell': 620.0, 'min_profit': 180.0},  # Increased for testing
    'dji mini 3 pro': {'max_buy': 400.0, 'min_buy': 86.0, 'target': 215.0, 'resell': 520.0, 'min_profit': 150.0},  # Increased for testing
    'dji mavic air 2': {'max_buy': 350.0, 'min_buy': 72.8, 'target': 182.0, 'resell': 460.0, 'min_profit': 140.0},  # Increased for testing
    'dji mini 2': {'max_buy': 250.0, 'min_buy': 50.8, 'target': 127.0, 'resell': 310.0, 'min_profit': 100.0},  # Increased for testing
    'pioneer ddj-flx10': {'max_buy': 1000.0, 'min_buy': 242.0, 'target': 605.0, 'resell': 1400.0, 'min_profit': 400.0},  # Increased for testing
    'pioneer ddj-1000': {'max_buy': 800.0, 'min_buy': 156.4, 'target': 391.0, 'resell': 950.0, 'min_profit': 300.0},  # Increased for testing
    'pioneer ddj-sx3': {'max_buy': 550.0, 'min_buy': 103.6, 'target': 259.0, 'resell': 650.0, 'min_profit': 220.0},  # Increased for testing
    'pioneer ddj-800': {'max_buy': 450.0, 'min_buy': 86.0, 'target': 215.0, 'resell': 550.0, 'min_profit': 200.0},  # Increased for testing
    'pioneer ddj-400': {'max_buy': 220.0, 'min_buy': 36.0, 'target': 90.0, 'resell': 250.0, 'min_profit': 100.0},  # Increased for testing
    'pioneer ddj-sb3': {'max_buy': 200.0, 'min_buy': 33.4, 'target': 83.5, 'resell': 220.0, 'min_profit': 80.0},  # Increased for testing
    'traktor s4': {'max_buy': 500.0, 'min_buy': 103.6, 'target': 259.0, 'resell': 650.0, 'min_profit': 220.0},  # Increased for testing
}

# MARKET DATA - Real resale values from Vinted/Gumtree
MARKET_DATA = {
    'gopro hero 12': {
        'standard': {'vinted': '£320-400', 'list_price': '£340-380'},
        'creator': {'vinted': '£380-450', 'list_price': '£400-430'},
    },
    'gopro hero 11': {
        'standard': {'vinted': '£250-320', 'list_price': '£270-300'},
        'creator': {'vinted': '£300-370', 'list_price': '£320-350'},
    },
    'gopro hero 10': {
        'standard': {'vinted': '£200-270', 'list_price': '£220-250'},
    },
    'gopro hero 9': {
        'standard': {'vinted': '£140-200', 'list_price': '£160-185'},
    },
    'gopro hero 8': {
        'standard': {'vinted': '£110-160', 'list_price': '£125-145'},
    },
    'dji mavic 2 pro': {
        'standard': {'vinted': '£650-900', 'list_price': '£700-850'},
        'fly more': {'vinted': '£800-1100', 'list_price': '£850-1000'},
    },
    'dji air 2s': {
        'standard': {'vinted': '£500-700', 'list_price': '£550-650'},
        'fly more': {'vinted': '£650-850', 'list_price': '£700-800'},
    },
    'dji mini 3 pro': {
        'standard': {'vinted': '£400-550', 'list_price': '£450-520'},
        'fly more': {'vinted': '£550-700', 'list_price': '£600-670'},
    },
    'dji mavic air 2': {
        'standard': {'vinted': '£350-500', 'list_price': '£400-470'},
        'fly more': {'vinted': '£480-630', 'list_price': '£520-600'},
    },
    'dji mini 2': {
        'standard': {'vinted': '£220-330', 'list_price': '£250-310'},
        'fly more': {'vinted': '£300-420', 'list_price': '£330-390'},
    },
    'pioneer ddj-flx10': {
        'standard': {'vinted': '£1200-1600', 'list_price': '£1300-1500'},
    },
    'pioneer ddj-1000': {
        'standard': {'vinted': '£800-1100', 'list_price': '£900-1050'},
    },
    'pioneer ddj-sx3': {
        'standard': {'vinted': '£550-750', 'list_price': '£600-700'},
    },
    'pioneer ddj-800': {
        'standard': {'vinted': '£450-650', 'list_price': '£500-600'},
    },
    'pioneer ddj-400': {
        'standard': {'vinted': '£200-280', 'list_price': '£220-260'},
    },
    'pioneer ddj-sb3': {
        'standard': {'vinted': '£180-250', 'list_price': '£200-240'},
    },
    'traktor s4': {
        'mk3': {'vinted': '£550-750', 'list_price': '£600-700'},
        'mk2': {'vinted': '£350-500', 'list_price': '£400-470'},
    },
}

def init_database():
    logger.info("🗄️ Initializing database...")
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            search_text TEXT,
            max_price REAL,
            min_price REAL,
            target_price REAL,
            resell_price REAL,
            min_profit REAL,
            brand TEXT DEFAULT 'Various',
            country TEXT DEFAULT 'co.uk',
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked TIMESTAMP,
            discord_webhook TEXT
        )
    """)
    logger.info("   ✅ search_queries table ready")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_items (
            id INTEGER PRIMARY KEY,
            search_query_id INTEGER,
            title TEXT,
            description TEXT,
            price REAL,
            currency TEXT,
            url TEXT,
            brand TEXT,
            user_login TEXT,
            photo_url TEXT,
            found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE,
            filter_reason TEXT,
            FOREIGN KEY (search_query_id) REFERENCES search_queries(id)
        )
    """)
    logger.info("   ✅ tracked_items table ready")
    
    try:
        cursor.execute("ALTER TABLE tracked_items ADD COLUMN description TEXT")
        logger.info("   ✅ Added description column")
    except sqlite3.OperationalError:
        logger.info("   ℹ️ Description column already exists")
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully\n")

def strict_product_match(title: str, product_key: str):
    """STRICT filtering based on TITLE ONLY - runs BEFORE web scraping"""
    title_lower = title.lower()
    logger.debug(f"      🔍 Filtering title: '{title[:50]}...'")
    
    if product_key not in PRODUCT_SPECS:
        logger.debug(f"      ❌ Product key '{product_key}' not in specs")
        return False, "Product not in specs"
    
    spec = PRODUCT_SPECS[product_key]
    
    # Check for critical excluded terms in title
    for term in CRITICAL_EXCLUSIONS_TITLE:
        if term in title_lower:
            logger.debug(f"      ❌ Found excluded term: '{term}'")
            return False, f"Excluded term: '{term}'"
    
    # Check for parts/accessories indicators
    parts_indicators = [
        'only', 'spare', 'replacement', 'accessory', 'accessories',
        'part', 'parts', 'component', 'addon', 'add-on'
    ]
    for indicator in parts_indicators:
        if indicator in title_lower and any(excl in title_lower for excl in ['case', 'bag', 'mount', 'battery', 'charger', 'cable', 'propeller', 'lens', 'remote']):
            logger.debug(f"      ❌ Found parts indicator: '{indicator}'")
            return False, f"Parts/accessories: '{indicator}'"
    
    # Title length check
    if len(title) < 10:
        logger.debug(f"      ❌ Title too short ({len(title)} chars)")
        return False, "Title too short"
    
    # Keyword match - check if ANY keyword appears in title
    keyword_match = False
    matched_keyword = None
    for keyword in spec['keywords']:
        # Check if keyword appears anywhere in title (more flexible)
        if keyword.lower() in title_lower or all(word in title_lower for word in keyword.lower().split()):
            keyword_match = True
            matched_keyword = keyword
            break
    
    if not keyword_match:
        logger.debug(f"      ❌ No keyword match from {spec['keywords']}")
        return False, "No keyword match"
    
    logger.debug(f"      ✅ Matched keyword: '{matched_keyword}'")
    
    # Exclusion check
    for exclude in spec['exclude']:
        if exclude.lower() in title_lower:
            logger.debug(f"      ❌ Found exclusion: '{exclude}'")
            return False, f"Excluded: '{exclude}'"
    
    # Must contain check
    if 'must_contain' in spec:
        for must_have in spec['must_contain']:
            found = False
            for term in spec['must_contain']:
                if term.lower() in title_lower:
                    found = True
                    logger.debug(f"      ✅ Found required term: '{term}'")
                    break
            if not found:
                logger.debug(f"      ❌ Missing required term from {spec['must_contain']}")
                return False, f"Missing required term"
            break
    
    logger.debug(f"      ✅ ALL FILTERS PASSED")
    return True, "Passed all filters"

def check_description_quality(description: str) -> Tuple[bool, str]:
    """Smart description filtering - only filters truly bad conditions"""
    if not description or description in ['No description found on page', 'Listing no longer available', 'Could not scrape (bot detection)']:
        return True, "No description to check"
    
    desc_lower = description.lower()
    logger.debug(f"         🔍 Checking description quality...")
    
    # Check for CRITICAL exclusions only
    for term in CRITICAL_EXCLUSIONS_DESCRIPTION:
        if term in desc_lower:
            logger.warning(f"         ❌ CRITICAL: Found '{term}' in description")
            return False, f"Bad condition: '{term}'"
    
    logger.debug(f"         ✅ Description passed quality check")
    return True, "Description OK"

def parse_bundle_type_from_title(title: str, product_key: str) -> str:
    """Extract bundle/version type from title"""
    title_lower = title.lower()
    
    # For GoPros
    if 'gopro' in product_key:
        if 'creator' in title_lower or 'creator edition' in title_lower:
            return 'creator'
        return 'standard'
    
    # For DJI Drones
    if 'dji' in product_key:
        if 'fly more' in title_lower or 'flymore' in title_lower or 'combo' in title_lower:
            return 'fly more'
        return 'standard'
    
    # For DJ Controllers (Traktor versions)
    if 'traktor' in product_key:
        if 'mk3' in title_lower or 'mk 3' in title_lower:
            return 'mk3'
        if 'mk2' in title_lower or 'mk 2' in title_lower:
            return 'mk2'
        return 'standard'
    
    return 'standard'

def parse_bundle_type_from_description(description: str, product_key: str) -> str:
    """Extract bundle/version type from description"""
    if not description:
        return 'standard'
    
    desc_lower = description.lower()
    
    # For GoPros
    if 'gopro' in product_key:
        if 'creator' in desc_lower or 'creator edition' in desc_lower:
            return 'creator'
    
    # For DJI Drones
    if 'dji' in product_key:
        if 'fly more' in desc_lower or 'flymore' in desc_lower or 'combo' in desc_lower:
            return 'fly more'
    
    # For DJ Controllers
    if 'traktor' in product_key:
        if 'mk3' in desc_lower or 'mk 3' in desc_lower:
            return 'mk3'
        if 'mk2' in desc_lower or 'mk 2' in desc_lower:
            return 'mk2'
    
    return 'standard'

def get_market_data(model_key: str, title: str, description: str = "") -> dict:
    """Get market pricing data for specific model and bundle type"""
    bundle_title = parse_bundle_type_from_title(title, model_key)
    bundle_desc = parse_bundle_type_from_description(description, model_key)
    
    # Prefer description detection over title
    bundle = bundle_desc if bundle_desc != 'standard' else bundle_title
    
    if model_key in MARKET_DATA:
        if bundle in MARKET_DATA[model_key]:
            return MARKET_DATA[model_key][bundle]
        elif 'standard' in MARKET_DATA[model_key]:
            return MARKET_DATA[model_key]['standard']
    
    return {'vinted': 'Not available', 'list_price': 'Not available'}

async def scrape_vinted_description(url: str, item_id: int, max_retries: int = 3) -> Tuple[str, bool]:
    """Scrape description from Vinted listing page - only called AFTER item passes filters"""
    logger.info(f"         🌐 Starting web scrape for item #{item_id}")
    logger.debug(f"         🔗 URL: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"         🔄 Attempt {attempt + 1}/{max_retries}")
            
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                logger.debug(f"         📡 Sending HTTP GET request...")
                response = await client.get(url, headers=headers)
                logger.debug(f"         📥 Response: HTTP {response.status_code}")
                
                if response.status_code == 200:
                    logger.debug(f"         ✅ Page loaded successfully ({len(response.text)} bytes)")
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Method 1: Meta description
                    logger.debug(f"         🔎 Method 1: Checking meta tags...")
                    meta_desc = soup.find('meta', {'property': 'og:description'})
                    if meta_desc and meta_desc.get('content'):
                        desc = meta_desc.get('content').strip()
                        if desc and len(desc) > 10:
                            logger.info(f"         ✅ Found description via meta tag ({len(desc)} chars)")
                            return desc, True
                    
                    # Method 2: JSON-LD schema
                    logger.debug(f"         🔎 Method 2: Checking JSON-LD schema...")
                    json_ld = soup.find('script', {'type': 'application/ld+json'})
                    if json_ld:
                        try:
                            data = json.loads(json_ld.string)
                            if isinstance(data, dict) and 'description' in data:
                                desc = data['description'].strip()
                                if desc and len(desc) > 10:
                                    logger.info(f"         ✅ Found description via JSON-LD ({len(desc)} chars)")
                                    return desc, True
                        except Exception as e:
                            logger.debug(f"         ⚠️ JSON-LD parse error: {e}")
                    
                    # Method 3: Common description selectors
                    logger.debug(f"         🔎 Method 3: Checking common div classes...")
                    description_selectors = [
                        {'class': 'details-list__item-value'},
                        {'class': 'item-description'},
                        {'class': 'description'},
                        {'itemprop': 'description'},
                        {'class': 'u-break-word'},
                    ]
                    
                    for selector in description_selectors:
                        desc_elem = soup.find('div', selector)
                        if desc_elem:
                            desc = desc_elem.get_text(strip=True)
                            if desc and len(desc) > 10:
                                logger.info(f"         ✅ Found description via selector {selector} ({len(desc)} chars)")
                                return desc, True
                    
                    # Method 4: Pattern matching
                    logger.debug(f"         🔎 Method 4: Pattern matching in page text...")
                    page_text = soup.get_text()
                    desc_pattern = r'Description[:\s]+(.{20,500}?)(?:\n\n|Item details|Reviews|Questions)'
                    match = re.search(desc_pattern, page_text, re.IGNORECASE | re.DOTALL)
                    if match:
                        desc = match.group(1).strip()
                        if desc and len(desc) > 10:
                            logger.info(f"         ✅ Found description via pattern match ({len(desc)} chars)")
                            return desc, True
                    
                    logger.warning(f"         ⚠️ No description found using any method")
                    return "No description found on page", False
                    
                elif response.status_code == 404:
                    logger.warning(f"         ❌ Listing not found (HTTP 404)")
                    return "Listing no longer available", False
                    
                elif response.status_code in [403, 406]:
                    logger.warning(f"         🚫 Bot detection (HTTP {response.status_code})")
                    if attempt < max_retries - 1:
                        wait_time = RETRY_DELAY * (attempt + 1)
                        logger.info(f"         ⏳ Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    return "Could not scrape (bot detection)", False
                    
                else:
                    logger.warning(f"         ⚠️ Unexpected HTTP {response.status_code}")
                    if attempt < max_retries - 1:
                        logger.info(f"         ⏳ Waiting {RETRY_DELAY}s before retry...")
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    return f"HTTP error {response.status_code}", False
                    
        except httpx.TimeoutException:
            logger.warning(f"         ⏱️ Request timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                logger.info(f"         ⏳ Waiting 5s before retry...")
                await asyncio.sleep(5)
                continue
            return "Scrape timeout", False
            
        except Exception as e:
            logger.error(f"         ❌ Scrape error: {e}")
            if attempt < max_retries - 1:
                logger.info(f"         ⏳ Waiting 5s before retry...")
                await asyncio.sleep(5)
                continue
            return f"Scrape error: {str(e)[:50]}", False
    
    logger.error(f"         ❌ Max retries exceeded for item #{item_id}")
    return "Max retries exceeded", False

async def send_discord_notification(webhook_url: str, item: dict, pricing: dict):
    try:
        logger.info(f"         📬 Preparing Discord notification...")
        
        # Get market data for this specific model
        model_key = item.get('model_key', '')
        description = item.get('description', '')
        market_data = get_market_data(model_key, item['title'], description)
        bundle_type = parse_bundle_type_from_description(description, model_key)
        if bundle_type == 'standard':
            bundle_type = parse_bundle_type_from_title(item['title'], model_key)
        
        # Calculate potential profit using Vinted range (take middle of range)
        vinted_str = market_data.get('vinted', '£0')
        try:
            if '-' in vinted_str and vinted_str != 'Not available':
                vinted_parts = vinted_str.replace('£', '').split('-')
                vinted_low = float(vinted_parts[0])
                vinted_high = float(vinted_parts[1])
                vinted_avg = (vinted_low + vinted_high) / 2
            else:
                vinted_avg = float(vinted_str.replace('£', '').replace(',', '').replace('Not available', '0'))
            profit = vinted_avg - item['price']
        except:
            profit = 0
        
        if profit >= 300:
            color = 0xFF0000
            logger.debug(f"         💎 HIGH PROFIT: £{profit:.0f}")
        elif profit >= 150:
            color = 0xFFA500
            logger.debug(f"         💰 GOOD PROFIT: £{profit:.0f}")
        else:
            color = 0x00FF00
            logger.debug(f"         💵 DECENT PROFIT: £{profit:.0f}")
        
        # Get category emoji
        if 'gopro' in model_key:
            emoji = '📷'
        elif 'dji' in model_key:
            emoji = '🚁'
        else:
            emoji = '🎧'
        
        title = f"{emoji} {item['title'][:100]}"
        
        description_text = item.get('description', '')
        if description_text and len(description_text) > 1500:
            description_text = description_text[:1500] + "... *(truncated)*"
            logger.debug(f"         ✂️ Description truncated to 1500 chars")
        
        embed_description = f"**[🛒 View on Vinted]({item['url']})**\n\n"
        
        if description_text and description_text not in ['', 'No description in listing', 'No description found on page', 'Listing no longer available', 'Could not scrape (bot detection)']:
            embed_description += f"📝 **Description:**\n{description_text}\n\n"
            logger.debug(f"         📝 Including description in embed")
        elif description_text in ['No description found on page', 'Listing no longer available']:
            embed_description += f"⚠️ *{description_text}*\n\n"
            logger.debug(f"         ⚠️ Adding warning: {description_text}")
        
        embed_description += f"👤 **Seller:** {item.get('user_login', 'Unknown')}\n"
        embed_description += f"📦 **Type:** {bundle_type.title()}"
        
        # Get listing date
        listing_date = item.get('photo_uploaded_at', 'Unknown')
        if listing_date and listing_date != 'Unknown':
            try:
                from datetime import datetime as dt
                if isinstance(listing_date, str):
                    listing_dt = dt.fromisoformat(listing_date.replace('Z', '+00:00'))
                    listing_date = listing_dt.strftime("%d %b %Y, %H:%M")
            except:
                pass
        
        embed = {
            "title": title,
            "description": embed_description,
            "color": color,
            "fields": [
                {"name": "💷 Listed Price", "value": f"£{item['price']}", "inline": True},
                {"name": "💰 Potential Profit", "value": f"£{profit:.0f}", "inline": True},
                {"name": "🏷️ Vinted Resell Range", "value": market_data.get('vinted', 'N/A'), "inline": True},
                {"name": "📅 Listed On Vinted", "value": listing_date, "inline": True},
                {"name": "🎯 Conservative List", "value": market_data.get('list_price', 'N/A'), "inline": True},
                {"name": "⏰ Found", "value": datetime.utcnow().strftime("%H:%M UTC"), "inline": True}
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Camera & DJ Bot {emoji} | Vinted Market Data"}
        }
        
        if item.get('photo_url'):
            embed["thumbnail"] = {"url": item['photo_url']}
            logger.debug(f"         🖼️ Added thumbnail image")
        
        payload = {"embeds": [embed], "username": f"Camera & DJ Pro {emoji}"}
        
        logger.debug(f"         📡 Sending to Discord webhook...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"         ✅ Discord notification sent successfully!")
            return True
            
    except Exception as e:
        logger.error(f"         ❌ Discord notification failed: {e}")
        return False

async def search_with_pagination(scraper, params, max_pages=MAX_PAGES_PER_SEARCH):
    logger.info(f"  🔎 Starting pagination search (max {max_pages} pages)")
    logger.debug(f"  📋 Search params: {params}")
    
    all_items = []
    consecutive_errors = 0
    session_errors = 0
    
    for page in range(1, max_pages + 1):
        retry_count = 0
        page_success = False
        
        while retry_count < MAX_RETRIES and not page_success:
            try:
                page_params = params.copy()
                page_params['page'] = page
                
                if retry_count > 0:
                    logger.info(f"  🔄 Retry {retry_count}/{MAX_RETRIES} for page {page}...")
                else:
                    logger.info(f"  📄 Fetching page {page}/{max_pages}...")
                
                items = await scraper.search(page_params)
                
                consecutive_errors = 0
                session_errors = 0
                page_success = True
                
                if not items or len(items) == 0:
                    logger.info(f"  ✅ No more items found - end reached at page {page}")
                    return all_items
                
                all_items.extend(items)
                logger.info(f"  ✅ Page {page}: Found {len(items)} items | Running total: {len(all_items)}")
                
                if page < max_pages and len(items) > 0:
                    logger.debug(f"  ⏳ Waiting {PAGE_DELAY}s before next page...")
                    await asyncio.sleep(PAGE_DELAY)
                    
            except Exception as e:
                error_msg = str(e)
                retry_count += 1
                logger.error(f"  ❌ Error on page {page}: {error_msg}")
                
                if '406' in error_msg or 'Not Acceptable' in error_msg:
                    session_errors += 1
                    logger.error(f"  🚫 Bot detection on page {page}!")
                    if session_errors >= 1:
                        logger.error(f"  ⛔ Bot detected - stopping search")
                        await asyncio.sleep(SESSION_RESET_DELAY)
                        return all_items
                    await asyncio.sleep(SESSION_RESET_DELAY)
                    break
                
                elif '403' in error_msg or 'Forbidden' in error_msg:
                    consecutive_errors += 1
                    logger.warning(f"  ⚠️ Rate limit on page {page}")
                    if consecutive_errors >= 2:
                        logger.error(f"  ⛔ Multiple rate limits - stopping")
                        await asyncio.sleep(RETRY_DELAY * 2)
                        return all_items
                    await asyncio.sleep(RETRY_DELAY)
                    if retry_count >= MAX_RETRIES:
                        break
                        
                elif '401' in error_msg or 'Unauthorized' in error_msg:
                    logger.warning(f"  ⚠️ Session expired on page {page}")
                    await asyncio.sleep(RETRY_DELAY)
                    if retry_count >= MAX_RETRIES:
                        logger.error(f"  ⛔ Session could not be renewed")
                        return all_items
                    
                else:
                    logger.error(f"  ❌ Unexpected error: {e}")
                    if retry_count >= MAX_RETRIES:
                        break
                    await asyncio.sleep(15)
    
    logger.info(f"  🎯 Search complete: Collected {len(all_items)} items")
    return all_items

async def create_filtered_searches():
    logger.info("📋 Setting up search queries in database...")
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM search_queries")
    existing_count = cursor.fetchone()[0]
    
    if existing_count >= len(PRICING_DATA):
        logger.info(f"✅ All {existing_count} products already in database")
        conn.close()
        return
    
    discord_webhook = "https://discordapp.com/api/webhooks/1422243737261707382/aoFqRx4rpIaplAGL96W8r19iCLrucHCt7gbdmK2hLzXP9q9QZO3pGJAi9OBqW1Ghunaz"
    
    cursor.execute("SELECT search_text FROM search_queries")
    existing_products = set(row[0] for row in cursor.fetchall())
    
    added_count = 0
    for product_key, pricing in PRICING_DATA.items():
        if product_key not in existing_products:
            logger.info(f"   ➕ Adding {product_key} to database")
            
            # Determine brand
            if 'gopro' in product_key:
                brand = 'GoPro'
            elif 'dji' in product_key:
                brand = 'DJI'
            elif 'pioneer' in product_key:
                brand = 'Pioneer'
            elif 'traktor' in product_key:
                brand = 'Native Instruments'
            else:
                brand = 'Various'
            
            cursor.execute("""
                INSERT INTO search_queries 
                (name, search_text, max_price, min_price, target_price, resell_price, min_profit, brand, country, enabled, discord_webhook)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (product_key.replace('-', ' ').title(), product_key, pricing['max_buy'], pricing['min_buy'],
                  pricing['target'], pricing['resell'], pricing['min_profit'], 
                  brand, "co.uk", True, discord_webhook))
            added_count += 1
    
    conn.commit()
    conn.close()
    
    if added_count > 0:
        logger.info(f"✅ Added {added_count} new products")
    logger.info(f"📦 Total tracked: {len(PRICING_DATA)}\n")

async def track_vinted_items():
    """Main tracking: Price Filter → Title Filter → Scrape Description → Quality Check → Discord"""
    logger.info("\n" + "="*60)
    logger.info("📷🚁🎧 CAMERA & DJ PRO BOT - NEW CYCLE STARTING")
    logger.info("="*60)
    logger.info(f"🕐 Cycle started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM search_queries WHERE enabled = TRUE")
    total_products = cursor.fetchone()[0]
    logger.info(f"📊 Total enabled products: {total_products}")
    
    cursor.execute(f"""
        SELECT * FROM search_queries 
        WHERE enabled = TRUE 
        ORDER BY last_checked ASC NULLS FIRST
        LIMIT {MAX_PRODUCTS_PER_CYCLE}
    """)
    queries = cursor.fetchall()
    
    if not queries:
        conn.close()
        logger.warning("⚠️ No enabled queries found")
        return
    
    logger.info(f"🎯 Checking {len(queries)}/{total_products} products this cycle\n")
    
    base_url = "https://www.vinted.co.uk"
    scraper = AsyncVintedScraper(base_url)
    
    cycle_stats = {
        'total_items': 0,
        'passed_title_filter': 0,
        'failed_description_check': 0,
        'total_filtered': 0,
        'descriptions_scraped': 0,
        'scrape_failures': 0,
        'discord_sent': 0,
        'already_tracked': 0
    }
    
    try:
        for idx, query in enumerate(queries, 1):
            query_id, name, search_text, max_price, min_price, target_price, resell_price, min_profit, brand, country, enabled, created_at, last_checked, discord_webhook = query
            
            # Get emoji based on product type
            if 'gopro' in search_text:
                emoji = '📷'
            elif 'dji' in search_text:
                emoji = '🚁'
            else:
                emoji = '🎧'
            
            logger.info(f"\n{'='*60}")
            logger.info(f"[{idx}/{len(queries)}] {emoji} PROCESSING: {name}")
            logger.info(f"{'='*60}")
            logger.info(f"💰 Price Range: £{min_price} - £{max_price}")
            logger.info(f"📊 Using Vinted/Gumtree Market Data")
            logger.info(f"📈 Min Profit Target: £{min_profit}")
            logger.info(f"🔍 Search Query: '{search_text}'")
            if last_checked:
                logger.info(f"⏰ Last Checked: {last_checked}")
            logger.info("")
            
            # Use broader search terms for better API results
            # Map product key to simpler search term
            search_term_map = {
                'gopro hero 12': 'gopro 12',
                'gopro hero 11': 'gopro 11',
                'gopro hero 10': 'gopro 10',
                'gopro hero 9': 'gopro 9',
                'gopro hero 8': 'gopro 8',
                'dji mavic 2 pro': 'mavic 2 pro',
                'dji air 2s': 'air 2s',
                'dji mini 3 pro': 'mini 3 pro',
                'dji mavic air 2': 'mavic air 2',
                'dji mini 2': 'dji mini 2',
                'pioneer ddj-flx10': 'ddj flx10',
                'pioneer ddj-1000': 'ddj 1000',
                'pioneer ddj-sx3': 'ddj sx3',
                'pioneer ddj-800': 'ddj 800',
                'pioneer ddj-400': 'ddj 400',
                'pioneer ddj-sb3': 'ddj sb3',
                'traktor s4': 'traktor s4',
            }
            
            api_search_term = search_term_map.get(search_text, search_text)
            
            params = {
                'search_text': api_search_term,
                'price_to': max_price,
                'price_from': min_price,
                # Removed catalog_ids - it's too restrictive, let keyword filtering handle it
                'order': 'newest_first'
            }
            
            # STEP 1: Get all items (price filtered by API)
            logger.info(f"🔎 STEP 1: Searching Vinted API...")
            logger.info(f"   🔍 API Search Term: '{api_search_term}' (mapped from '{search_text}')")
            logger.info(f"   💰 Price Filter: £{min_price} - £{max_price}")
            items = await search_with_pagination(scraper, params)
            cycle_stats['total_items'] += len(items)
            logger.info(f"✅ API returned {len(items)} items\n")
            
            product_filtered = 0
            product_passed = 0
            product_already_tracked = 0
            
            logger.info(f"🔬 STEP 2: Applying title filters to {len(items)} items...")
            logger.info(f"{'─'*60}\n")
            
            for item_idx, item in enumerate(items, 1):
                try:
                    item_id = item.id
                    
                    # Check if already tracked
                    cursor.execute("SELECT id FROM tracked_items WHERE id = ?", (item_id,))
                    if cursor.fetchone():
                        product_already_tracked += 1
                        cycle_stats['already_tracked'] += 1
                        logger.debug(f"   ⭐ Item #{item_id} already tracked - skipping")
                        continue
                    
                    title = item.title or 'No title'
                    item_url = item.url or f"{base_url}/items/{item_id}"
                    price = item.price or 0
                    
                    logger.info(f"   📦 [{item_idx}/{len(items)}] Item #{item_id}")
                    logger.info(f"      🏷 Title: {title[:70]}")
                    logger.info(f"      💷 Price: £{price}")
                    
                    # STEP 2: Title filter
                    logger.debug(f"      🔎 Running title filter...")
                    passes_filter, filter_reason = strict_product_match(title, search_text)
                    
                    if not passes_filter:
                        product_filtered += 1
                        cycle_stats['total_filtered'] += 1
                        logger.info(f"      ❌ FILTERED OUT: {filter_reason}\n")
                        continue
                    
                    # STEP 3: PASSED filters - calculate profit estimate (without description yet)
                    product_passed += 1
                    cycle_stats['passed_title_filter'] += 1
                    
                    market_data_preview = get_market_data(search_text, title, "")
                    try:
                        vinted_str = market_data_preview.get('vinted', '£0')
                        if '-' in vinted_str and vinted_str != 'Not available':
                            vinted_parts = vinted_str.replace('£', '').split('-')
                            vinted_low = float(vinted_parts[0])
                            vinted_high = float(vinted_parts[1])
                            vinted_avg = (vinted_low + vinted_high) / 2
                        else:
                            vinted_avg = 0
                        profit = vinted_avg - price
                    except:
                        profit = 0
                    
                    logger.info(f"      ✅ ✅ ✅ PASSED ALL FILTERS! ✅ ✅ ✅")
                    logger.info(f"      💰 Potential Profit: £{profit:.0f}")
                    logger.info(f"      🌐 STEP 3: Scraping listing page...")
                    
                    description, scrape_success = await scrape_vinted_description(item_url, item_id)
                    
                    if scrape_success:
                        cycle_stats['descriptions_scraped'] += 1
                        logger.info(f"         ✅ Description scraped!")
                        logger.info(f"         📝 Preview: {description[:120]}{'...' if len(description) > 120 else ''}")
                    else:
                        cycle_stats['scrape_failures'] += 1
                        logger.warning(f"         ⚠️ Scrape issue: {description}")
                    
                    # STEP 4: Check description quality
                    logger.info(f"         🔍 Checking description for critical issues...")
                    desc_passes, desc_reason = check_description_quality(description)
                    
                    if not desc_passes:
                        product_filtered += 1
                        cycle_stats['total_filtered'] += 1
                        cycle_stats['failed_description_check'] += 1
                        logger.warning(f"         ❌ DESCRIPTION FAILED: {desc_reason}")
                        logger.info(f"         ⛔ Item rejected\n")
                        continue
                    
                    logger.info(f"         ✅ Description quality check passed!")
                    
                    # Re-calculate profit with description for better bundle detection
                    market_data_final = get_market_data(search_text, title, description)
                    bundle_final = parse_bundle_type_from_description(description, search_text)
                    if bundle_final == 'standard':
                        bundle_final = parse_bundle_type_from_title(title, search_text)
                    try:
                        vinted_str_final = market_data_final.get('vinted', '£0')
                        if '-' in vinted_str_final and vinted_str_final != 'Not available':
                            vinted_parts = vinted_str_final.replace('£', '').split('-')
                            vinted_low = float(vinted_parts[0])
                            vinted_high = float(vinted_parts[1])
                            vinted_avg_final = (vinted_low + vinted_high) / 2
                            profit = vinted_avg_final - price
                        else:
                            profit = 0
                    except:
                        profit = 0
                    
                    logger.info(f"         📦 Detected type: {bundle_final.title()}")
                    
                    # STEP 5: Prepare item data
                    logger.info(f"         📦 Preparing item data...")
                    
                    # Extract listing date
                    listing_date = 'Unknown'
                    if hasattr(item, 'photo') and hasattr(item.photo, 'high_resolution'):
                        if hasattr(item.photo.high_resolution, 'timestamp'):
                            listing_date = item.photo.high_resolution.timestamp
                    elif hasattr(item, 'photo_uploaded_at'):
                        listing_date = item.photo_uploaded_at
                    
                    item_data = {
                        'id': item_id,
                        'title': title,
                        'description': description,
                        'price': price,
                        'currency': item.currency or 'GBP',
                        'url': item_url,
                        'brand': item.brand_title if hasattr(item, 'brand_title') and item.brand_title else brand,
                        'user_login': item.user.login if hasattr(item, 'user') and item.user else None,
                        'photo_url': item.photos[0].url if hasattr(item, 'photos') and item.photos and len(item.photos) > 0 else None,
                        'model_key': search_text,
                        'photo_uploaded_at': listing_date
                    }
                    
                    pricing_info = {
                        'target': target_price,
                        'resell': resell_price,
                        'min_profit': min_profit
                    }
                    
                    # Save to database
                    logger.info(f"         💾 Saving to database...")
                    cursor.execute("""
                        INSERT INTO tracked_items 
                        (id, search_query_id, title, description, price, currency, url, brand, user_login, photo_url, filter_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (item_data['id'], query_id, item_data['title'], item_data['description'],
                          item_data['price'], item_data['currency'], item_data['url'],
                          item_data['brand'], item_data['user_login'], item_data['photo_url'], filter_reason))
                    logger.info(f"         ✅ Saved to database")
                    
                    # STEP 6: Send to Discord
                    logger.info(f"         📬 STEP 5: Sending to Discord...")
                    discord_success = await send_discord_notification(discord_webhook, item_data, pricing_info)
                    
                    if discord_success:
                        cycle_stats['discord_sent'] += 1
                        logger.info(f"         🎉 🎉 🎉 SUCCESS! Deal posted to Discord! 🎉 🎉 🎉")
                        logger.info(f"         💎 Estimated Profit: £{profit:.0f} | Listed: £{price} | Vinted Range: {market_data_preview.get('vinted', 'N/A')}")
                    else:
                        logger.error(f"         ❌ Failed to send Discord notification")
                    
                    logger.info("")
                    
                    # Delay between items
                    if product_passed < len(items):
                        logger.debug(f"      ⏳ Waiting {SCRAPE_DELAY}s...")
                        await asyncio.sleep(SCRAPE_DELAY)
                    
                except Exception as e:
                    logger.error(f"      ❌ Error processing item #{item.id}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    continue
            
            logger.info(f"\n{'─'*60}")
            logger.info(f"📊 {name} - Summary:")
            logger.info(f"   📦 Total scanned: {len(items)}")
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
        logger.info(f"📊 CYCLE COMPLETE - Camera & DJ Pro Bot")
        logger.info(f"{'='*60}")
        logger.info(f"🕐 Completed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f"")
        logger.info(f"📈 Cycle Statistics:")
        logger.info(f"   📦 Total items scanned: {cycle_stats['total_items']:,}")
        logger.info(f"   ⭐ Already tracked: {cycle_stats['already_tracked']}")
        logger.info(f"   ✅ Passed title filters: {cycle_stats['passed_title_filter']}")
        logger.info(f"   📝 Descriptions scraped: {cycle_stats['descriptions_scraped']}")
        logger.info(f"   ⚠️ Failed description check: {cycle_stats['failed_description_check']}")
        logger.info(f"   ⚠️ Scrape failures: {cycle_stats['scrape_failures']}")
        logger.info(f"   ❌ Total filtered out: {cycle_stats['total_filtered']:,}")
        logger.info(f"   📬 Posted to Discord: {cycle_stats['discord_sent']}")
        logger.info(f"   🔄 Products checked: {len(queries)}/{total_products}")
        logger.info(f"")
        logger.info(f"⏰ Next cycle in: {CYCLE_INTERVAL//60} minutes")
        logger.info(f"{'='*60}\n")

async def scheduler():
    logger.info("🔄 Scheduler started")
    cycle_number = 0
    
    while True:
        try:
            cycle_number += 1
            logger.info(f"\n📢 Starting Cycle #{cycle_number}")
            await track_vinted_items()
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info(f"💤 Sleeping for {CYCLE_INTERVAL}s ({CYCLE_INTERVAL//60} minutes)...")
        logger.info(f"{'─'*60}\n")
        await asyncio.sleep(CYCLE_INTERVAL)

@app.on_event("startup")
async def startup_event():
    logger.info("\n" + "="*60)
    logger.info("📷🚁🎧 CAMERA & DJ PRO BOT - STARTING UP")
    logger.info("="*60)
    logger.info(f"🕐 Startup: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("")
    
    init_database()
    await create_filtered_searches()
    
    logger.info(f"⚙️ BOT CONFIGURATION:")
    logger.info(f"   📷 GoPro Models: Hero 8, 9, 10, 11, 12")
    logger.info(f"   🚁 DJI Drones: Mini 2, Mini 3 Pro, Air 2S, Mavic Air 2, Mavic 2 Pro")
    logger.info(f"   🎧 DJ Controllers: Pioneer DDJ series, Traktor S4")
    logger.info(f"   🎯 Total products tracked: {len(PRICING_DATA)}")
    logger.info(f"   📝 Max pages per search: {MAX_PAGES_PER_SEARCH}")
    logger.info(f"   📄 Items per page: ~{ITEMS_PER_PAGE}")
    logger.info(f"   📦 Max items per product: ~{MAX_PAGES_PER_SEARCH * ITEMS_PER_PAGE}")
    logger.info(f"   🔄 Products per cycle: {MAX_PRODUCTS_PER_CYCLE}")
    logger.info(f"   ⏱️ Cycle interval: {CYCLE_INTERVAL//60} minutes")
    logger.info(f"   ⏳ Page delay: {PAGE_DELAY}s")
    logger.info(f"   ⏳ Product delay: {PRODUCT_DELAY}s")
    logger.info(f"   ⏳ Scrape delay: {SCRAPE_DELAY}s")
    logger.info(f"   💰 Pricing: Realistic profit margins")
    logger.info(f"   ⚡ Speed: Faster scraping (4s pages, 3s items, 12s products)")
    logger.info(f"")
    logger.info(f"🎯 FILTERING FLOW:")
    logger.info(f"   1️⃣ Price Filter (Vinted API)")
    logger.info(f"   2️⃣ Title Filter (Keywords + Exclusions)")
    logger.info(f"   3️⃣ ✅ GREEN LIGHT → Web Scrape Description")
    logger.info(f"   4️⃣ 🔍 Description Quality Check (Critical Issues Only)")
    logger.info(f"   5️⃣ 📬 Post to Discord with Vinted Market Data")
    logger.info(f"")
    logger.info(f"📊 Market Data: Vinted/Gumtree pricing only")
    logger.info(f"🔍 Title Exclusions: {len(CRITICAL_EXCLUSIONS_TITLE)} terms")
    logger.info(f"🔍 Description Exclusions: {len(CRITICAL_EXCLUSIONS_DESCRIPTION)} critical conditions")
    logger.info(f"📊 Database: {DATABASE_FILE}")
    logger.info(f"={'='*60}\n")
    
    logger.info("🚀 Starting scheduler task...")
    asyncio.create_task(scheduler())
    logger.info("✅ Bot is now running!\n")

@app.get("/", response_class=HTMLResponse)
async def home():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM tracked_items")
    total_items = cursor.fetchone()[0]
    
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
    
    conn.close()
    
    html = f"""
    <html>
        <head>
            <title>Camera & DJ Pro Bot</title>
            <style>
                body {{ font-family: Arial; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); min-height: 100vh; padding: 20px; }}
                .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 40px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }}
                h1 {{ color: #333; font-size: 42px; margin-bottom: 10px; }}
                .subtitle {{ color: #666; font-size: 18px; margin-bottom: 30px; }}
                .badge {{ background: #4CAF50; color: white; padding: 5px 15px; border-radius: 15px; font-size: 12px; font-weight: bold; }}
                .flow {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .flow-step {{ display: flex; align-items: center; margin: 10px 0; }}
                .flow-number {{ background: #f5576c; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 15px; }}
                .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
                .stat {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 30px; border-radius: 15px; text-align: center; color: white; }}
                .stat h3 {{ font-size: 14px; opacity: 0.9; text-transform: uppercase; margin-bottom: 10px; }}
                .stat p {{ font-size: 48px; font-weight: bold; margin: 0; }}
                .products {{ margin-top: 30px; }}
                .products h2 {{ color: #333; margin-bottom: 20px; }}
                .product {{ padding: 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }}
                .product-name {{ font-weight: 600; }}
                .product-count {{ background: #f5576c; color: white; padding: 8px 20px; border-radius: 25px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📷🚁🎧 Camera & DJ Pro Bot</h1>
                <p class="subtitle">GoPros, DJI Drones & DJ Controllers <span class="badge">VINTED MARKET DATA 🏷️</span></p>
                
                <div class="flow">
                    <h3 style="margin-top: 0;">🎯 Filtering Flow:</h3>
                    <div class="flow-step"><div class="flow-number">1</div><div>Price Filter (Vinted API)</div></div>
                    <div class="flow-step"><div class="flow-number">2</div><div>Title Filter (Keywords + Exclusions)</div></div>
                    <div class="flow-step"><div class="flow-number">3</div><div>✅ GREEN LIGHT → Scrape Description</div></div>
                    <div class="flow-step"><div class="flow-number">4</div><div>🔍 Description Quality Check</div></div>
                    <div class="flow-step"><div class="flow-number">5</div><div>📬 Post with Vinted Data</div></div>
                </div>
                
                <div class="stats">
                    <div class="stat">
                        <h3>Total Deals</h3>
                        <p>{total_items}</p>
                    </div>
                    <div class="stat">
                        <h3>Products Tracked</h3>
                        <p>{len(PRICING_DATA)}</p>
                    </div>
                </div>
                
                <div class="products">
                    <h2>📊 Top Product Deals</h2>
                    {''.join([f'<div class="product"><span class="product-name">{name}</span><span class="product-count">{count}</span></div>' for name, count in top_products]) if top_products else '<p>No deals yet...</p>'}
                </div>
            </div>
        </body>
    </html>
    """
    return html

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot": "camera_dj_pro",
        "products": len(PRICING_DATA),
        "categories": ["gopro", "dji", "dj_controllers"],
        "features": ["comprehensive_logging", "smart_scraping", "description_quality_check", "two_tier_filtering", "vinted_market_data", "listing_dates"]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8003))
    logger.info(f"🚀 Starting FastAPI server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
