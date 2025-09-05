"""Orchestrator: scrape -> save -> analyze -> promote accepted posts.

Usage: set APIFY_TOKEN and ensure local Ollama LLM is running at http://localhost:11434
"""
from datetime import datetime, timedelta
from backend.scraper import Scraper, PostScraper
from backend.database import DB
from backend.analyzer import LLMAnalizer
from backend.telegram_bot import BOT
import logging
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

load_dotenv()

def main():

    # Simple wrapper for CLI usage
    result = run_pipeline()
    logging.info('Run finished: %d accepted items', len(result))
    return result


def run_pipeline(apify_token=None, db_path=None, start_time = None, telegram_notification = True, lookback_minutes=60, limit=5):
    """Run one pipeline iteration and return the list of accepted items.

    This function is import-friendly for servers or schedulers.
    Inputs via params fall back to environment variables when None.
    Returns: list of accepted item dicts (may be empty).
    """
    # Lightweight config
    apify_token = apify_token or os.getenv('APIFY_TOKEN')
    db_path = db_path or os.getenv('DB_PATH', 'facebook_posts.db')
    lookback_minutes = int(os.getenv('LOOKBACK_MINUTES', str(lookback_minutes)))
    limit = int(os.getenv('SCRAPE_LIMIT', str(limit)))
    llama_model = os.getenv('OLLAMA_MODEL', 'llama3:latest')
    scraper_type = os.getenv('SCRAPE_TYPE', 'group')
    query = os.getenv('SCRAPE_QUERY', 'affitti torino')

    # Compute start time: onlyPostsNewerThan expects ISO-like string
    if scraper_type == 'group':
        start_time = start_time or (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S.000')
        id_string = "id"
        scraper = Scraper(start_time=start_time, limit=limit, apify_token=apify_token)
    elif scraper_type == 'post':
        start_time = start_time or (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        id_string = "post_id"
        scraper = PostScraper(start_time=start_time, query=query, limit=limit, apify_token=apify_token)
    else:
        raise ValueError(f"Invalid scraper type: {scraper_type}, set scraper type to 'group' or 'post' in .env file")
    logging.info('Scraping starts at %s', start_time)
    
    db = DB(path=db_path)
    analyzer = LLMAnalizer(llama_model)
    bot = BOT()

    # Scrape
    items = scraper.scrape()
    if not items:
        logging.info('No items scraped; exiting.')
        return []
    if len(items) == 1 and items == [{'error': 'no_items', 'errorDescription': 'Empty or private data for provided input'}]:
        logging.info('No items found; exiting.')
        return []

    # Save all scraped items to main table
    count = db.add_items_to_db(items, table='facebook_posts')
    logging.info('Saved %d items to facebook_posts on a total of %d', len(items)-count, len(items))

    # Analyze items and promote accepted ones to good_facebook_posts
    accepted = []
    for item in items:
        try:
            analysis = analyzer.analize_post(item)
            # Normalise keys: analyzer returns {"stato":..., "motivo":...} per prompt
            status = analysis.get('stato') or analysis.get('status') or analysis.get('state')
            motivo = analysis.get('motivo') or analysis.get('motivation') or analysis.get('motivo', '')
            item['status'] = status
            item['motivo'] = motivo

            if isinstance(status, str) and status.strip().upper() == 'ACCETTATO':
                accepted.append(item)
                db.add_items_to_db([item], table='good_facebook_posts')
                if telegram_notification:
                    bot.send_message(f"Nuovo post accettato: {item.get('text')}\n url:\n {item.get('url')}")

            db.update_item_field(item.get(id_string), 'status', status)
            db.update_item_field(item.get(id_string), 'motivo', motivo)

        except Exception as e:
            logging.exception('Analysis failed for item id=%s: %s', item.get('id'), e)

    if accepted:
        logging.info('Promoted %d items to good_facebook_posts', len(accepted))
    else:
        logging.info('No items accepted by analyzer')

    return accepted


def analyze_pending(db_path=None, limit=100, telegram_notification=True):
    """Analyze only posts whose status is NULL in facebook_posts.
    Returns list of accepted item dicts (may be empty).
    """
    # Config
    db_path = db_path or os.getenv('DB_PATH', 'facebook_posts.db')
    llama_model = os.getenv('OLLAMA_MODEL', 'llama3:latest')

    db = DB(path=db_path)
    analyzer = LLMAnalizer(llama_model)
    bot = BOT()

    # Fetch pending items
    items = db.fetch_items_with_null_status(limit=limit)
    if not items:
        logging.info('No pending items with NULL status found')
        return []

    accepted = []
    count = 0
    for item in items:
        count += 1
        try:
            analysis = analyzer.analize_post(item)
            status = (analysis.get('stato') or analysis.get('status') or analysis.get('state'))
            motivo = (analysis.get('motivo') or analysis.get('motivation') or analysis.get('motivo', ''))
            item['status'] = status
            item['motivo'] = motivo

            if isinstance(status, str) and status.strip().upper() == 'ACCETTATO':
                accepted.append(item)
                db.add_items_to_db([item], table='good_facebook_posts')
                if telegram_notification:
                    bot.send_message(f"Nuovo post accettato: {item.get('text')}\n url: {item.get('url')}")

            id_string = "id" if item.get('id') else "post_id"
            db.update_item_field(item.get(id_string), 'status', status)
            db.update_item_field(item.get(id_string), 'motivo', motivo)
            logging.info('Updated item %d of %d', count, len(items))
        except Exception as e:
            logging.exception('Analysis failed for pending item id=%s: %s', item.get('id'), e)

    if accepted:
        logging.info('Pending analysis promoted %d items to good_facebook_posts', len(accepted))
    else:
        logging.info('No pending items accepted by analyzer')

    return accepted


if __name__ == '__main__':
    main()
