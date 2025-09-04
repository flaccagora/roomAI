from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import os
import requests

# Replace with your BotFather token
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class BOT():
    def __init__(self, chat_id = None, base_url = None):
        if chat_id:
            self.chat_id = chat_id
        else:
            self.chat_id = CHAT_ID
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = BASE_URL
    
    def send_message(self, text: str) -> dict:
        """
        Send a message via Telegram Bot API.

        Args:
        text (str): The message content.

        Returns:
            dict: JSON response from Telegram API.
        """
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"  # allows bold, italics, links
        }
        response = requests.post(url, json=payload)
        return response.json()


if __name__ == "__main__":
    bot = BOT(CHAT_ID)
    result = bot.send_message("Hello from <b>Python</b> 🚀")
    print(result)
