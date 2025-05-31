import configparser


def load_config():
    config = configparser.ConfigParser()
    config.read("config.ini")

    return {
        "api_id": int(config["Telegram"]["api_id"]),
        "api_hash": config["Telegram"]["api_hash"],
        "username": config["Telegram"]["username"],
        "target_channel": config["Telegram"]["target_channel"],
        "bot_token": config["Bot"]["bot_token"],
        "bot_username": config["Bot"]["bot_username"],
        "bot_chat_id": config["Bot"]["bot_chat_id"],
    }


SELECTED_CHATS = [
    "@rand2ch",
    "@grotesque_tg",
    "@axaxanakanecta",
    "@gvonotestsh",
    "@profunctor_io",
    "@ttttttttttttsdsd",
    "@dsasdadsasda",
]

LUBA_CHAT = "@Shanova_uuu"
