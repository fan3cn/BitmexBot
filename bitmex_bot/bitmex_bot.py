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
from policy import Policy
from bitmex_bot.utils.util import last_5mins

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
            if order['ordType'] == "Stop":
                logger.info("Canceling: %s %s %d @ %.*f" % (order['ordType'], order['side'], order['orderQty'],  tickLog, order['stopPx']))
            if order['ordType'] == "Limit":
                logger.info("Canceling: %s %s %d @ %.*f" % (order['ordType'], order['side'], order['orderQty'], tickLog, order['price']))

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
    signals = [signal.SIGINT, signal.SIGHUP, signal.SIGTERM, signal.SIGKILL]

    def __init__(self):
        self.exchange = ExchangeInterface()
        atexit.register(self.exit)
        [signal.signal(s, self.exit) for s in self.signals]
        self.current_bitmex_price = 0
        logger.info("-------------------------------------------------------------")
        logger.info("Starting Bot......")
        self.policy = Policy()
        self.policy.logger = log.setup_OHLC_logger("policy")
        # self.trade_signal = self.policy.trade_signal()
        # price at which bot enters first order
        self.last_price = 0
        # to store current prices for per bot run
        self.amount = settings.POSITION
        self.is_trade = False
        self.order_price = 0
        self.stop_price = 0
        self.profit_price = 0
        self.last_order_min = -1
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
        #self.exchange.set_isolate_margin()
        # set the leverage
        self.exchange.set_leverage()

    # self.place_orders()

    def reset(self):
        self.exchange.cancel_all_orders()
        self.sanity_check()
        self.print_status()
        if settings.DRY_RUN:
            print("Yes, we exit")
            sys.exit()

    def print_status(self):
        """Print the current MM status."""
        margin1 = self.exchange.get_margin()
        self.running_qty = self.exchange.get_delta()
        self.start_XBt = margin1["marginBalance"]

        ratio = XBt_to_XBT(self.start_XBt) / settings.INITIAL_BALANCE
        if ratio <= settings.STOP_BALANCE_RATIO:
            raise errors.HugeLossError("U have lost %.2f%% of the initial fund, we stop here." % ((1 - settings.STOP_BALANCE_RATIO) * 100))
        ROE = (XBt_to_XBT(self.start_XBt) - settings.INITIAL_BALANCE) / settings.INITIAL_BALANCE
        logger.info("Current XBT Balance : %.6f, ROE : %.3f%%" % (XBt_to_XBT(self.start_XBt), ROE*100))
        # logger.info("Contracts Traded This Run by BOT: %d" % (self.running_qty - self.starting_qty1))
        # logger.info("Total Contract Delta: %.4f XBT" % self.exchange.calc_delta()['spot'])

    def get_ticker(self):
        ticker = self.exchange.get_ticker()
        return ticker

    ###
    # Orders
    ###

    def place_orders(self, **kwargs):
        """Create order items for use in convergence."""
        if not settings.PLACE_ORDER:
            logger.info("You are NOT in PLACE_ORDER mode, skip placing order...")
            order = {}
            order['price'] = self.last_price
            return order
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
        # Get latest trade price
        self.get_exchange_price()
        # Fetch the last 5 min trade data
        self.policy.fetch_historical_data()
        # Get trade signal
        self.signal = self.policy.trade_signal()
        # Current open position
        self.position = self.exchange.get_position()
        logger.info(
            "Current Price is {}, trade signal: {}, position: {}".format(self.last_price, self.signal, self.position))
        # Last order is executed, cancel all orders(StopLimit/Limit)
        if self.is_trade and self.position == 0:
            self.exchange.cancel_all_orders()
            self.is_trade = False
            self.order_price = 0
            self.stop_price = 0
            self.profit_price = 0
            #self.last_order_min = -1
            # self.last_order_direction = self.policy.TREND_FLAT

        # Logging open position info
        if self.position != 0:
            logger.info("Holding position {}, \tOrder price {} \tStop Price {} \tProfit Price {} ".
                        format(self.position, self.order_price, self.stop_price, self.profit_price))

        if self.check_if_order():
            if self.signal == constants.UP:
                logger.info("Buy Trade Signal {}".format(self.last_price))
                logger.info("-----------------------------------------")
                self.is_trade = True
                order = self.place_orders(side=self.BUY, orderType='Market', quantity=self.amount)
                if settings.STOP_PROFIT_FACTOR != "":
                    self.profit_price = round(order['price'] + settings.STOP_PROFIT_FACTOR, 2)
                if settings.STOP_LOSS_FACTOR != "":
                    self.stop_price = round(order['price'] - settings.STOP_LOSS_FACTOR, 2)
                # Long
                self.last_order_direction = constants.UP
                self.order_price = order['price']
                logger.info("Order price {} \tStop Price {} \tProfit Price {} ".
                            format(order['price'], self.stop_price, self.profit_price))
                sleep(settings.API_REST_INTERVAL)

                if settings.STOP_LOSS_FACTOR != "":
                    #
                    # A Stop Market order. Specify an orderQty and stopPx.
                    # When the stopPx is reached, the order will be entered into the book.
                    # On sell orders, the order will trigger if the triggering price is lower than the stopPx.
                    # On buys, higher.
                    # Note: Stop orders do not consume margin until triggered. Be sure that the required margin is available in your account so that it may trigger fully.
                    # Close Stops don't require an orderQty. See Execution Instructions below.
                    self.place_orders(side=self.SELL, orderType='Stop', quantity=self.amount,
                                      stopPx=self.stop_price)
                    sleep(settings.API_REST_INTERVAL)

                if settings.STOP_PROFIT_FACTOR != "":
                    self.place_orders(side=self.SELL, orderType='Limit', quantity=self.amount,
                                      price=self.profit_price)
                    sleep(settings.API_REST_INTERVAL)

                self.last_order_min = last_5mins()


            elif self.signal == constants.DOWN:
                logger.info("Sell Trade Signal {}".format(self.last_price))
                logger.info("-----------------------------------------")
                self.is_trade = True
                self.sequence = self.SELL
                # place order
                order = self.place_orders(side=self.SELL, orderType='Market', quantity=self.amount)

                if settings.STOP_PROFIT_FACTOR != "":
                    self.profit_price = round(order['price'] - settings.STOP_PROFIT_FACTOR, 2)
                if settings.STOP_LOSS_FACTOR != "":
                    self.stop_price = round(order['price'] + settings.STOP_LOSS_FACTOR, 2)

                self.last_order_direction = constants.DOWN
                self.order_price = order['price']

                logger.info("Order price {} \tStop Price {} \tProfit Price {} ".
                            format(order['price'], self.stop_price, self.profit_price))
                sleep(settings.API_REST_INTERVAL)
                if settings.STOP_LOSS_FACTOR != "":
                    self.place_orders(side=self.BUY, orderType='Stop', quantity=self.amount,
                                      stopPx=self.stop_price)
                    sleep(settings.API_REST_INTERVAL)
                if settings.STOP_PROFIT_FACTOR != "":
                    self.place_orders(side=self.BUY, orderType='Limit', quantity=self.amount,
                                      price=self.profit_price)
                    sleep(settings.API_REST_INTERVAL)

                self.last_order_min = last_5mins()

    # 检查当前时间是否适合开单
    def check_if_order(self):
        # 不能在同一个5分钟内连续开单
        # 判断是否下单错误
        return not self.is_trade and self.position == 0 and last_5mins() != self.last_order_min

    def check_file_change(self):
        """Restart if any files we're watching have changed."""
        for f, mtime in watched_files_mtimes:
            if getmtime(f) > mtime:
                self.restart()

    def check_connection(self):
        """Ensure the WS connections are still open."""
        return self.exchange.is_open()

    def exit(self, signalnum, frame):
        logger.info("Shutting down. All open orders will be cancelled.")
        try:
            if self.position == 0:
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

            logger.info("--------------------")

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
