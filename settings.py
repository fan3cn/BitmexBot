from os.path import join
import logging

BASE_URL_LIVE = "https://www.bitmex.com/api/v1/"

BASE_URL_TESTING = "https://testnet.bitmex.com/api/v1/"

# The BitMEX API requires permanent API keys. Go to https://testnet.bitmex.com/api/apiKeys to fill these out.
# for TESTING mode
# https://www.bitmex.com/api/apiKeys for LIVE mode
API_KEY = "HkrGARbQaw6SAXUKskmZGgXj"
API_SECRET = "-StPBQFePPZ7xi4cg0i3cGV0z8JOqEaehsYaGcN0Kv8o4yps"


# Instrument to market make on BitMEX.
SYMBOL = "XBTUSD"

# order amount for bitmex in USD
POSITION = 1000

# tick interval used for mcad data
TICK_INTERVAL = '1m'

STOP_LOSS_FACTOR = 0.007
STOP_PROFIT_FACTOR = 0.01
# There is two mode one is TESTING and other is LIVE
MODE = "TESTING"

INTERVAL = 0.005

RELIST_INTERVAL = 0.01

CHECK_POSITION_LIMITS = False
MIN_POSITION = -10000
MAX_POSITION = 10000

LOOP_INTERVAL = 5

# Wait times between orders / errors
API_REST_INTERVAL = 1
API_ERROR_INTERVAL = 10


# Available levels: logging.(DEBUG|INFO|WARN|ERROR)
LOG_LEVEL = logging.INFO
ORDERID_PREFIX = "sam_bitmex_"

# If any of these files (and this file) changes, reload the bot.
WATCHED_FILES = [join("bitmex_bot", f) for f in ["bitmex_bot.py", "bitmex_historical.py", __file__]]

ONE_MILLION = 1000000
RULE_1_DOWN_VOLUME = 1 * ONE_MILLION
RULE_1_DOWN_VOLUME_RATIO = 3
RULE_1_DOWN_TRADE_GAP =1.2
RULE_1_UP_VOLUME = 2 * ONE_MILLION
RULE_1_UP_VOLUME_RATIO = 3
RULE_1_UP_TRADE_GAP = 1.2
RULE_2_DOWN_TRADE_GAP = 0.8
RULE_2_UP_TRADE_GAP = 0.8
RULE_3_CONSECUTIVE_UP = 5
RULE_3_CONSECUTIVE_DOWN = 4
RULE_3_HEAD_TAIL_GAP_UP = 2.0
RULE_3_HEAD_TAIL_GAP_DOWN =2.0
RULE_4_SURGE_VOLUME = 6 * ONE_MILLION
RULE_4_SURGE_TRADE_GAP = 3
RULE_4_PLUNGE_VOLUME = 6 * ONE_MILLION
RULE_4_PLUNGE_TRADE_GAP = 3