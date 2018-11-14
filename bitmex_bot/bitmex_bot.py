from __future__ import absolute_import

import threading
from time import sleep
import sys
from datetime import datetime
from os.path import getmtime
import atexit
import signal
from bitmex_bot import bitmex, indicators
from bitmex_bot.settings import settings
from bitmex_bot.utils import log, constants, errors
from bitmex_bot.bitmex_historical import Bitmex
from policy import Policy
import logging
from bitmex_bot.bot_trade import BOT_TRADE

# Used for reloading the bot - saves modified times of key files
import os

watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]

#
# Helpers
#


logger = log.setup_custom_logger('root')

class ExchangeInterface:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        if len(sys.argv) > 1:
            self.symbol = sys.argv[1]
        else:
            self.symbol = settings.SYMBOL

        url = settings.BASE_URL_TESTING

        # mode in which mode you want to run your bot
        self.mode = settings.MODE

        if self.mode == "LIVE":
            url = settings.BASE_URL_LIVE

        self.bitmex = bitmex.BitMEX(base_url=url, symbol=self.symbol,
                                    apiKey=settings.API_KEY, apiSecret=settings.API_SECRET,
                                    orderIDPrefix=settings.ORDERID_PREFIX, leverage=settings.LEVERAGE)

    def cancel_order(self, order):
        tickLog = self.get_instrument()['tickLog']
        logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))
        while True:
            try:
                self.bitmex.cancel(order['orderID'])
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def cancel_all_orders(self):
        logger.info("Resetting current position. Canceling all existing orders.")
        tickLog = self.get_instrument()['tickLog']

        orders_1 = self.bitmex.http_open_orders()

        for order in orders_1:
            logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))

        if len(orders_1):
            self.bitmex.cancel([order['orderID'] for order in orders_1])

        sleep(settings.API_REST_INTERVAL)

    def get_user_balance(self):
        return self.bitmex.user_balance()

    def get_delta(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.get_position(symbol)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.instrument(symbol)

    def get_margin(self):
        return self.bitmex.funds()

    def get_orders(self):
        return self.bitmex.open_orders()

    def set_isolate_margin(self):
        self.bitmex.isolate_margin(self.symbol)

    def get_highest_buy(self):
        buys = [o for o in self.get_orders() if o['side'] == 'Buy']
        if not len(buys):
            return {'price': -2 ** 32}
        highest_buy = max(buys or [], key=lambda o: o['price'])
        return highest_buy if highest_buy else {'price': -2 ** 32}

    def get_lowest_sell(self):
        sells = [o for o in self.get_orders() if o['side'] == 'Sell']
        if not len(sells):
            return {'price': 2 ** 32}
        lowest_sell = min(sells or [], key=lambda o: o['price'])
        return lowest_sell if lowest_sell else {'price': 2 ** 32}  # ought to be enough for anyone

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.position(symbol)['currentQty']

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.ticker_data(symbol)

    def close_position(self):
        return self.bitmex.close_position()

    def is_open(self):
        """Check that websockets are still open."""
        return not self.bitmex.ws.exited

    def check_market_open(self):
        instrument = self.get_instrument()
        if instrument["state"] != "Open" and instrument["state"] != "Closed":
            raise errors.MarketClosedError("The instrument %s is not open. State: %s" %
                                           (self.symbol, instrument["state"]))

    def check_if_orderbook_empty(self):
        """This function checks whether the order book is empty"""
        instrument = self.get_instrument()
        if instrument['midPrice'] is None:
            raise errors.MarketEmptyError("Orderbook is empty, cannot quote")

    def amend_bulk_orders(self, orders):
        return self.bitmex.amend_bulk_orders(orders)

    def create_bulk_orders(self, orders):
        return self.bitmex.create_bulk_orders(orders)

    def cancel_bulk_orders(self, orders):
        return self.bitmex.cancel([order['orderID'] for order in orders])

    def place_order(self, **kwargs):
        """
        :param kwargs:
        :return:
        """
        if kwargs['side'] == 'buy':
            kwargs.pop('side')
            return self.bitmex.buy(**kwargs)

        elif kwargs['side'] == 'sell':
            kwargs.pop('side')
            return self.bitmex.sell(**kwargs)

    def set_leverage(self):
        return self.bitmex.set_leverage()

class OrderManager:
    UP = "up"
    DOWN = "down"
    SELL = "sell"
    BUY = "buy"

    def __init__(self):
        self.exchange = ExchangeInterface()
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)
        self.current_bitmex_price = 0
        logger.info("-------------------------------------------------------------")
        logger.info("Starting Bot......")
        self.policy = Policy()
        self.policy.logger = log.setup_OHLC_logger("policy")
        #self.trade_signal = self.policy.trade_signal()
        # price at which bot enters first order
        self.last_price = 0
        # to store current prices for per bot run
        self.amount = settings.POSITION
        self.is_trade = False
        self.stop_price = 0
        self.profit_price = 0
        logger.info("Using symbol %s." % self.exchange.symbol)

    def init(self):
        if settings.DRY_RUN:
            logger.info("Initializing dry run. Orders printed below represent what would be posted to BitMEX.")
        else:
            logger.info("Order Manager initializing, connecting to BitMEX. Live run: executing real trades.")
        self.start_time = datetime.now()
        self.instrument = self.exchange.get_instrument()
        self.starting_qty1 = self.exchange.get_delta()
        self.running_qty = self.starting_qty1
        self.reset()
        # set cross margin for the trade
        self.exchange.set_isolate_margin()
        # set the leverage
        self.exchange.set_leverage()

    # self.place_orders()

    def reset(self):
        self.exchange.cancel_all_orders()
        self.sanity_check()
        self.print_status()
        if settings.DRY_RUN:
            sys.exit()

    def print_status(self):
        """Print the current MM status."""
        margin1 = self.exchange.get_margin()
        self.running_qty = self.exchange.get_delta()
        self.start_XBt = margin1["marginBalance"]
        logger.info("Current XBT Balance : %.6f" % XBt_to_XBT(self.start_XBt))
        logger.info("Contracts Traded This Run by BOT: %d" % (self.running_qty - self.starting_qty1))
        #logger.info("Total Contract Delta: %.4f XBT" % self.exchange.calc_delta()['spot'])

    def get_ticker(self):
        ticker = self.exchange.get_ticker()
        return ticker

    ###
    # Orders
    ###

    def place_orders(self, **kwargs):
        """Create order items for use in convergence."""
        return self.exchange.place_order(**kwargs)

    ###
    # Position Limits
    ###

    def short_position_limit_exceeded(self):
        "Returns True if the short position limit is exceeded"
        if not settings.CHECK_POSITION_LIMITS:
            return False
        position = self.exchange.get_delta()
        return position <= settings.MIN_POSITION

    def long_position_limit_exceeded(self):
        "Returns True if the long position limit is exceeded"
        if not settings.CHECK_POSITION_LIMITS:
            return False
        position = self.exchange.get_delta()
        # print(position)
        return position >= settings.MAX_POSITION

    def get_exchange_price(self):
        data = self.get_ticker()
        self.current_bid_price = data['buy']
        self.current_ask_price = data['sell']
        # price = float(self.current_ask_price+self.current_bid_price)/2
        price = data['buy']
        # if not (price == self.price_list[-1]):
        self.last_price = price

    ###
    # Sanity
    ##

    def sanity_check(self):
        """Perform checks before placing orders."""

        # Check if OB is empty - if so, can't quote.
        self.exchange.check_if_orderbook_empty()
        # Ensure market is still open.
        self.exchange.check_market_open()

        self.get_exchange_price()
        # print(self.exchange.get_orders())
        logger.info("current BITMEX price is {}".format(self.last_price))
        # self.get_exchange_price()
        self.policy.fetch_historical_data()

        signal = self.policy.trade_signal()

        position = self.exchange.get_position()

        logger.info("Current Price is {}, trade signal: {}, position: {}".format(self.last_price, signal, position))

        if self.is_trade and position == 0:
            self.exchange.cancel_all_orders()
            self.is_trade = False

        if not self.is_trade:
            if signal == self.policy.TREND_UP:
                logger.info("Buy Trade Signal {}".format(self.last_price))
                logger.info("-----------------------------------------")
                self.is_trade = True
                order = self.place_orders(side=self.BUY, orderType='Market', quantity=self.amount)
                if settings.STOP_PROFIT_FACTOR != "":
                    self.profit_price = order['price'] + settings.STOP_PROFIT_FACTOR
                if settings.STOP_LOSS_FACTOR != "":
                    self.stop_price = order['price'] - settings.STOP_LOSS_FACTOR
                print("Order price {} \tStop Price {} \tProfit Price {} ".
                      format(order['price'], self.stop_price, self.profit_price))
                sleep(settings.API_REST_INTERVAL)

                if settings.STOP_LOSS_FACTOR != "":
                    self.place_orders(side=self.SELL, orderType='StopLimit', quantity=self.amount,
                                      price=self.stop_price, stopPx=self.stop_price)
                    sleep(settings.API_REST_INTERVAL)

                if settings.STOP_PROFIT_FACTOR != "":
                    self.place_orders(side=self.SELL, orderType='Limit', quantity=self.amount,
                                      price=self.profit_price)
                    sleep(settings.API_REST_INTERVAL)

            elif signal == self.policy.TREND_DOWN:
                logger.info("Sell Trade Signal {}".format(self.last_price))
                logger.info("-----------------------------------------")
                self.is_trade = True
                self.sequence = self.SELL
                # place order
                order = self.place_orders(side=self.SELL, orderType='Market', quantity=self.amount)

                if settings.STOP_PROFIT_FACTOR != "":
                    self.profit_price = order['price'] - settings.STOP_PROFIT_FACTOR
                if settings.STOP_LOSS_FACTOR != "":
                    self.stop_price = order['price'] + settings.STOP_LOSS_FACTOR

                print("Order price {} \tStop Price {} \tProfit Price {} ".
                      format(order['price'], self.stop_price, self.profit_price))
                sleep(settings.API_REST_INTERVAL)
                if settings.STOP_LOSS_FACTOR != "":
                    self.place_orders(side=self.BUY, orderType='StopLimit', quantity=self.amount,
                                      price=self.stop_price, stopPx=self.stop_price)
                    sleep(settings.API_REST_INTERVAL)
                if settings.STOP_PROFIT_FACTOR != "":
                    self.place_orders(side=self.BUY, orderType='Limit', quantity=self.amount,
                                      price=self.profit_price)
                    sleep(settings.API_REST_INTERVAL)

    def check_file_change(self):
        """Restart if any files we're watching have changed."""
        for f, mtime in watched_files_mtimes:
            if getmtime(f) > mtime:
                self.restart()

    def check_connection(self):
        """Ensure the WS connections are still open."""
        return self.exchange.is_open()

    def exit(self):
        logger.info("Shutting down. All open orders will be cancelled.")
        try:
            self.exchange.cancel_all_orders()
            self.exchange.bitmex.exit()
        except errors.AuthenticationError as e:
            logger.info("Was not authenticated; could not cancel orders.")
        except Exception as e:
            logger.info("Unable to cancel orders: %s" % e)

        sys.exit()

    def run_loop(self):
        while True:
            sys.stdout.write("-----\n")
            sys.stdout.flush()

            self.check_file_change()
            sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
            if not self.check_connection():
                logger.error("Realtime data connection unexpectedly closed, restarting.")
                self.restart()

            self.sanity_check()  # Ensures health of mm - several cut-out points here
            self.print_status()  # Print skew, delta, etc

    def restart(self):
        logger.info("Restarting the bitmex bot...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


#
# Helpers
#


def XBt_to_XBT(XBt):
    return float(XBt) / constants.XBt_TO_XBT


def cost(instrument, quantity, price):
    mult = instrument["multiplier"]
    P = mult * price if mult >= 0 else mult / price
    return abs(quantity * P)


def margin(instrument, quantity, price):
    return cost(instrument, quantity, price) * instrument["initMargin"]


def run():
    logger.info('BitMEX bot Version: %s\n' % constants.VERSION)

    om = OrderManager()
    # om.exchange.get_user_balance()
    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        try:
            om.init()
            om.run_loop()
        except (KeyboardInterrupt, SystemExit):
            sys.exit()
    except Exception as e:
        logger.error(e)
    finally:
        sleep(1000)
