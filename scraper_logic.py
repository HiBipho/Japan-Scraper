import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import json
import sqlite3
import logging
from typing import List, Dict, Optional
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] - %(message)s')

class DatabaseManager:
    """Mengelola semua operasi database SQLite."""
    def __init__(self, db_name="listings.db"):
        # Path ini akan menunjuk ke Disk Persisten di Render, atau direktori lokal jika di Termux
        data_dir = os.environ.get('RENDER_DISK_PATH', '.')
        self.db_name = os.path.join(data_dir, db_name)
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.setup_tables()

    def setup_tables(self):
        """Membuat tabel jika belum ada."""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL UNIQUE
                )
            """)

    def get_keywords(self) -> List[str]:
        """Mengambil semua kata kunci dari database."""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT keyword FROM keywords ORDER BY keyword")
            return [row[0] for row in cursor.fetchall()]

    def add_keyword(self, keyword: str) -> bool:
        """Menambahkan kata kunci baru."""
        with self.conn:
            try:
                self.conn.execute("INSERT OR IGNORE INTO keywords (keyword) VALUES (?)", (keyword,))
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_keyword_and_listings(self, keyword: str) -> bool:
        """Menghapus keyword DAN semua listing yang mengandung keyword tersebut."""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
            keyword_deleted = cursor.rowcount > 0
            search_term = f"%{keyword}%"
            cursor.execute("DELETE FROM listings WHERE title LIKE ?", (search_term,))
            return keyword_deleted

    def get_listings(self, sort_by='date', order='desc') -> List[Dict]:
        """Mengambil data dengan opsi pengurutan."""
        allowed_sort_by = {'date': 'scraped_at', 'price': "CAST(REPLACE(REPLACE(price, '¥', ''), ',', '') AS INTEGER)"}
        allowed_order = {'asc': 'ASC', 'desc': 'DESC'}
        sort_column = allowed_sort_by.get(sort_by, 'scraped_at')
        sort_order = allowed_order.get(order, 'DESC')
        
        query = f"SELECT source, title, price, url, scraped_at FROM listings ORDER BY {sort_column} {sort_order}"
        
        with self.conn:
            self.conn.row_factory = sqlite3.Row
            cursor = self.conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def save_listings_and_get_new(self, listings: list) -> list:
        """Menyimpan item baru dan mengembalikannya untuk notifikasi."""
        if not listings: return []
        new_items = []
        sql = "INSERT OR IGNORE INTO listings (source, title, price, url) VALUES (?, ?, ?, ?)"
        with self.conn:
            cursor = self.conn.cursor()
            for item in listings:
                cursor.execute(sql, (item['source'], item['title'], item['price'], item['url']))
                if cursor.rowcount > 0:
                    new_items.append(item)
        return new_items

class Scraper:
    """Kelas dasar untuk semua scraper."""
    HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'}
    SOURCE_NAME = "Unknown"
    def scrape(self, query: str) -> List[Dict]: raise NotImplementedError
    def _get_response(self, url: str) -> Optional[requests.Response]:
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=15)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logging.error(f"[{self.SOURCE_NAME}] Gagal mengakses URL {url}: {e}")
            return None

class MercariScraper(Scraper):
    """Scraper yang diperbarui untuk Mercari."""
    SOURCE_NAME = "Mercari"
    def scrape(self, query: str) -> List[Dict]:
        url = f"https://jp.mercari.com/search?keyword={quote_plus(query)}&status=on_sale"
        response = self._get_response(url)
        if not response: return []
        results = []
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            json_scripts = soup.find_all('script', {'type': 'application/json'})
            for script in json_scripts:
                data = json.loads(script.string)
                items = data.get('props', {}).get('pageProps', {}).get('pageData', {}).get('searchPage', {}).get('items', [])
                if not items: continue
                for item in items:
                    item_id, name, price = item.get('id'), item.get('name'), item.get('price')
                    if all([item_id, name, price]):
                        results.append({'source': self.SOURCE_NAME, 'title': name, 'price': f"¥{price:,}", 'url': f"https://jp.mercari.com/item/{item_id}"})
                if results: break
        except Exception as e:
            logging.error(f"[{self.SOURCE_NAME}] Gagal parsing data. Error: {e}")
        return results

class YahooAuctionScraper(Scraper):
    """Scraper untuk Yahoo Auctions."""
    SOURCE_NAME = "Yahoo Auctions"
    def scrape(self, query: str) -> List[Dict]:
        url = f"https://auctions.yahoo.co.jp/search/search?p={quote_plus(query)}&va={quote_plus(query)}"
        response = self._get_response(url)
        if not response: return []
        results = []
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            products = soup.select('li.Product')
            for product in products:
                title_el, price_el = product.select_one('a.Product__titleLink'), product.select_one('.Product__priceValue')
                if title_el and price_el:
                    results.append({'source': self.SOURCE_NAME, 'title': title_el.get_text(strip=True), 'price': price_el.get_text(strip=True), 'url': title_el.get('href')})
        except Exception as e:
            logging.error(f"[{self.SOURCE_NAME}] Gagal parsing HTML. Error: {e}")
        return results
