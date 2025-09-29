
# Конфигурация TON Trading Bot

# Telegram Bot Token

TELEGRAM_TOKEN = "8158233940:AAEKdtZF1M7DX7IEnJHETY7MXMaOBURb7bw"

# TON API

TON_API_KEY = "8b96ada0392ea0c769cb81c4533ea7cfac76dfbaed3cb3bded9cc22b738ec3cf"

# ВАШ РЕАЛЬНЫЙ КОШЕЛЕК

WALLET_CONFIG = {

    "wallet_address": "UQAQ-bnS1chsJJKXFbmkrHTmn5L8SeKLnPzhNpqMLWKKbewh",

    "private_key": "01deec4979392d5b3729e5ffeba4162e68c783fe2182b11e15791e95289fefbf",

    "demo_mode": False,  # ВЫКЛЮЧАЕМ демо режим для реальных сделок

}

# Токены

TOKENS = {

    "TON": "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c",

    "USDT": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",

    "SCALE": "EQBlqsm144Dq6SjbPI4jjZvA1hqTIP3CvHovbIfW_t-SCALE",

    "NOT": "EQAvlWFDxGF2lXm67y4yzC17wYKD9A0guwPkMs1gOsM__NOT"

}

# Итоговая конфигурация

TRADING_CONFIG = {

    "ton_api_key": TON_API_KEY,

    "tokens": TOKENS,

    **WALLET_CONFIG

}

