#!/usr/bin/env python3
"""
BOT 3: Camera & DJ Pro
Tracks: GoPros, DJI Drones, DJ Controllers
"""

import asyncio
import sqlite3
import logging
import os
from datetime import datetime
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    from vinted_scraper import AsyncVintedScraper
except ImportError:
    class AsyncVintedScraper:
        def __init__(self, base_url):
            self.base_url = base_url
        async def search(self, params):
            return []

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Camera & DJ Bot")
DATABASE_FILE = "camera_dj_bot.db"

# CONFIGURATION
MAX_PAGES_PER_SEARCH = 12
PAGE_DELAY = 6
PRODUCT_DELAY = 15
CYCLE_INTERVAL = 900
MAX_PRODUCTS_PER_CYCLE = 5
SESSION_RESET_DELAY = 60

EXCLUDED_TERMS = ['broken', 'damaged', 'faulty', 'not working', 'for parts', 'repair', 'case', 'bag', 'mount only', 'battery only']

PRODUCT_SPECS = {
    # GoPro
    'gopro hero 12': {'keywords': ['hero 12', 'hero12'], 'exclude': ['11', '10', '9', '8', 'case', 'mount'], 'must_contain': ['gopro', 'hero']},
    'gopro hero 11': {'keywords': ['hero 11', 'hero11'], 'exclude': ['12', '10', '9', '8', 'case', 'mount'], 'must_contain': ['gopro', 'hero']},
    'gopro hero 10': {'keywords': ['hero 10', 'hero10'], 'exclude': ['12', '11', '9', '8', 'case', 'mount'], 'must_contain': ['gopro', 'hero']},
    'gopro hero 9': {'keywords': ['hero 9', 'hero9'], 'exclude': ['12', '11', '10', '8', 'case', 'mount'], 'must_contain': ['gopro', 'hero']},
    'gopro hero 8': {'keywords': ['hero 8', 'hero8'], 'exclude': ['12', '11', '10', '9', 'case', 'mount'], 'must_contain': ['gopro', 'hero']},
    
    # DJI Drones
    'dji mavic 2 pro': {'keywords': ['mavic 2 pro'], 'exclude': ['mini', 'air', 'case', 'bag'], 'must_contain': ['dji', 'mavic']},
    'dji air 2s': {'keywords': ['air 2s'], 'exclude': ['mini', 'mavic', 'case', 'bag'], 'must_contain': ['dji', 'air']},
    'dji mini 3 pro': {'keywords': ['mini 3 pro'], 'exclude': ['mini 2', 'mini 4', 'case', 'bag'], 'must_contain': ['dji', 'mini']},
    'dji mavic air 2': {'keywords': ['mavic air 2'], 'exclude': ['mini', 'case', 'bag'], 'must_contain': ['dji', 'mavic']},
    'dji mini 2': {'keywords': ['mini 2'], 'exclude': ['mini 3', 'mini 4', 'case', 'bag'], 'must_contain': ['dji', 'mini']},
    
    # DJ Controllers
    'pioneer ddj-flx10': {'keywords': ['ddj-flx10', 'ddj flx10', 'flx10'], 'exclude': ['case', 'bag'], 'must_contain': ['pioneer', 'ddj']},
    'pioneer ddj-1000': {'keywords': ['ddj-1000', 'ddj 1000'], 'exclude': ['800', '400', 'case', 'bag'], 'must_contain': ['pioneer', 'ddj']},
    'pioneer ddj-sx3': {'keywords': ['ddj-sx3', 'ddj sx3'], 'exclude': ['sb3', 'case', 'bag'], 'must_contain': ['pioneer', 'ddj']},
    'pioneer ddj-800': {'keywords': ['ddj-800', 'ddj 800'], 'exclude': ['1000', '400', 'case', 'bag'], 'must_contain': ['pioneer', 'ddj']},
    'pioneer ddj-400': {'keywords': ['ddj-400', 'ddj 400'], 'exclude': ['800', '1000', 'case', 'bag'], 'must_contain': ['pioneer', 'ddj']},
    'pioneer ddj-sb3': {'keywords': ['ddj-sb3', 'ddj sb3'], 'exclude': ['sx3', 'case', 'bag'], 'must_contain': ['pioneer', 'ddj']},
    'traktor s4': {'keywords': ['traktor s4', 'kontrol s4'], 'exclude': ['case', 'bag'], 'must_contain': ['traktor', 'kontrol']},
}

PRICING_DATA = {
    'gopro hero 12': {'max_buy': 220.0, 'min_buy': 59.6, 'target': 149.0, 'resell': 360.0, 'min_profit': 200.0},
    'gopro hero 11': {'max_buy': 174.6, 'min_buy': 46.4, 'target': 116.0, 'resell': 290.0, 'min_profit': 163.0},
    'gopro hero 10': {'max_buy': 136.1, 'min_buy': 36.0, 'target': 90.0, 'resell': 235.0, 'min_profit': 136.0},
    'gopro hero 9': {'max_buy': 99.0, 'min_buy': 26.4, 'target': 66.0, 'resell': 175.0, 'min_profit': 103.0},
    'gopro hero 8': {'max_buy': 72.9, 'min_buy': 19.2, 'target': 48.0, 'resell': 135.0, 'min_profit': 82.0},
    'dji mavic 2 pro': {'max_buy': 499.1, 'min_buy': 134.4, 'target': 336.0, 'resell': 820.0, 'min_profit': 457.0},
    'dji air 2s': {'max_buy': 386.4, 'min_buy': 103.6, 'target': 259.0, 'resell': 620.0, 'min_profit': 339.0},
    'dji mini 3 pro': {'max_buy': 317.6, 'min_buy': 86.0, 'target': 215.0, 'resell': 520.0, 'min_profit': 289.0},
    'dji mavic air 2': {'max_buy': 272.3, 'min_buy': 72.8, 'target': 182.0, 'resell': 460.0, 'min_profit': 262.0},
    'dji mini 2': {'max_buy': 189.8, 'min_buy': 50.8, 'target': 127.0, 'resell': 310.0, 'min_profit': 172.0},
    'pioneer ddj-flx10': {'max_buy': 900.6, 'min_buy': 242.0, 'target': 605.0, 'resell': 1400.0, 'min_profit': 745.0},
    'pioneer ddj-1000': {'max_buy': 583.0, 'min_buy': 156.4, 'target': 391.0,
