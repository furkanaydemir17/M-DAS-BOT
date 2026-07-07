import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        # Default config in case it is deleted
        default_config = {
            "telegram_token": "",
            "telegram_chat_id": "",
            "scan_interval_minutes": 15,
            "bist_tickers": ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS"],
            "crypto_tickers": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            "indicators": {
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "supertrend_period": 10,
                "supertrend_multiplier": 3.0
            }
        }
        save_config(default_config)
        return default_config
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config_data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

def update_telegram_settings(token: str, chat_id: str):
    config = load_config()
    config["telegram_token"] = token
    config["telegram_chat_id"] = chat_id
    save_config(config)

def update_tickers(bist_list, crypto_list):
    config = load_config()
    config["bist_tickers"] = bist_list
    config["crypto_tickers"] = crypto_list
    save_config(config)

def update_indicators(indicators_dict):
    config = load_config()
    config["indicators"].update(indicators_dict)
    save_config(config)
