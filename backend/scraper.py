from apify_client import ApifyClient
from datetime import datetime
import os
import logging
import json
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)


class Scraper():
    def __init__(self, start_time, limit=5, apify_token=None):
        # Allow token injection via env or parameter
        token = apify_token or os.getenv('APIFY_TOKEN')
        if not token:
            raise RuntimeError('Apify token not provided via APIFY_TOKEN env or apify_token param')

        # get the urls from the urls_to_scrape.txt file
        with open('./backend/urls_to_scrape.json', 'r') as f:
            self.start_urls = json.load(f)
        
        print(self.start_urls)

        self.client = ApifyClient(token)

        # Prepare the Actor input
        self.run_input = {
            "startUrls": self.start_urls,
            "resultsLimit": limit,
            "viewOption": "CHRONOLOGICAL",
            "onlyPostsNewerThan": start_time
        }

    def scrape(self):
        # Run the Apify actor and collect items from dataset
        run = self.client.actor("2chN8UQcH1CfxLRNE").call(run_input=self.run_input)

        items = []
        for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
            items.append(item)

        self.items = items

        # update run input so that it doesn't scrape the same posts again
        self.run_input["onlyPostsNewerThan"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000")

        logging.info('Scraped %d items', len(items))
        # print(items)
        return items
    def get_run_items(self, run_id):
        run = self.client.dataset(run_id).iterate_items()
        return run

if __name__ == "__main__":
    from datetime import datetime , timedelta
    start_time = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S.000')
    print('Scraping starts at %s', start_time)
    scraper = Scraper(start_time=start_time, limit=1)
    # scraper.scrape()
    # print(scraper.items[0])
    items = scraper.get_run_items("wQhVk1oOIFHBKpN24")
    for item in items:
        print(item)
        break