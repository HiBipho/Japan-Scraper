from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import configparser

from scraper_logic import DatabaseManager, MercariScraper, YahooAuctionScraper

# --- Konfigurasi ---
config = configparser.ConfigParser()
config.read('config.ini')
TELEGRAM_TOKEN = config['Telegram']['Token']
TELEGRAM_CHAT_ID = config['Telegram']['ChatID']
SERVER_HOST = config['Server']['Host']
SERVER_PORT = int(config['Server']['Port'])

app = Flask(__name__)
db_manager = DatabaseManager()
logging.getLogger('apscheduler').setLevel(logging.WARNING)

def send_telegram_notification(new_items_list):
    # ... (Tidak ada perubahan di fungsi ini)
    if not new_items_list or "TOKEN_API" in TELEGRAM_TOKEN: return
    try:
        import telegram
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        message_text = f"🔥 Ditemukan {len(new_items_list)} item baru!\n\n"
        for item in new_items_list[:10]:
            title = item['title'][:50] + '...' if len(item['title']) > 50 else item['title']
            message_text += f"*{item['source']}*\n[{title}]({item['url']})\nHarga: {item['price']}\n\n"
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message_text, parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)
        logging.info(f"Notifikasi Telegram untuk {len(new_items_list)} item berhasil dikirim.")
    except Exception as e:
        logging.error(f"Gagal mengirim notifikasi Telegram: {e}")

def run_master_scrape():
    # ... (Tidak ada perubahan di fungsi ini)
    logging.info("--- Memulai Sesi Scraping Otomatis ---")
    keywords = db_manager.get_keywords()
    if not keywords:
        logging.warning("Tidak ada kata kunci. Melewatkan scraping.")
        return
    scrapers = [MercariScraper(), YahooAuctionScraper()]
    all_results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = { executor.submit(scraper.scrape, keyword): (scraper.SOURCE_NAME, keyword) for keyword in keywords for scraper in scrapers }
        for future in as_completed(future_to_task):
            try:
                results = future.result()
                if results: all_results.extend(results)
            except Exception as e:
                logging.error(f"Error pada future scraping: {e}")
    if all_results:
        new_items = db_manager.save_listings_and_get_new(all_results)
        if new_items:
            logging.info(f"Scraping selesai. Ditemukan {len(new_items)} item baru.")
            send_telegram_notification(new_items)
        else:
            logging.info("Scraping selesai. Tidak ada item baru ditemukan.")
    else:
        logging.info("Scraping selesai. Tidak ada item baru.")
    logging.info("--- Sesi Scraping Otomatis Selesai ---")

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/listings', methods=['GET'])
def get_listings(): return jsonify(db_manager.get_listings())

@app.route('/api/keywords', methods=['GET', 'POST'])
def manage_keywords():
    if request.method == 'POST':
        keyword = request.json.get('keyword')
        if keyword:
            db_manager.add_keyword(keyword.strip())
            return jsonify({'status': 'success', 'keyword': keyword})
        return jsonify({'status': 'error', 'message': 'Keyword cannot be empty'}), 400
    return jsonify(db_manager.get_keywords())

# --- [PERBAIKAN] Rute delete diubah untuk memanggil fungsi baru ---
@app.route('/api/keywords/delete', methods=['POST'])
def delete_keyword():
    keyword = request.json.get('keyword')
    if keyword and db_manager.delete_keyword_and_listings(keyword):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Keyword not found'}), 404

@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    scheduler.add_job(run_master_scrape, 'date', id='manual_scrape_trigger', replace_existing=True)
    return jsonify({'status': 'Scraping job triggered'})

if __name__ == '__main__':
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(run_master_scrape, 'date')
    scheduler.add_job(run_master_scrape, 'interval', hours=1, id='hourly_scrape')
    scheduler.start()
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
