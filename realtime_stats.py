import logging
from collections import deque
from time import sleep

MAX_INTEGER = 10000000

class RealtimeStats():
    def __init__(self, ws):
        self.logger = logging.getLogger('RealtimeStats')
        self.ws = ws
        # keep last 60 second trade price
        self.prices = deque(maxlen=60)
        self.price_change = 0.0
        self.price_change_rate = 0.0
        self.last_price = 0.0
        self.high = 0.0
        self.low = MAX_INTEGER

        # trade volume
        self.buy_size = 0.0
        self.sell_size = 0.0
        self.total_size = 0.0
        self.buy_sell_size_ratio = 1.0

        # trade count
        self.buy_count = 0.0
        self.sell_count = 0.0
        self.total_count = 0.0
        self.buy_sell_count_ratio = 1.0

    def __del__(self):
        self.exit()

    def exit(self):
        self.exited = True

    def run(self):
        self.logger.info("Stats running...")
        # calculate on real-time trade data every SEC.
        while (self.ws.ws.sock.connected):
            trades = self.trades = self.ws.recent_trades()
            buy_size = sell_size = buy_count = sell_count = 0
            for trade in trades:
                if trade['side'] == "Buy":
                    buy_size += trade['size']
                    buy_count += 1
                else:
                    sell_size += trade['size']
                    sell_count += 1
                self.last_price = trade['price']

            self.prices.append(self.last_price)
            self.price_change = self.last_price - self.prices[0]
            self.price_change_rate = self.price_change / self.prices[0] if self.prices[0] > 0 else 0.0
            self.high = self.last_price if self.last_price > self.high else self.high
            self.low = self.last_price if self.last_price < self.low else self.low

            self.buy_size = buy_size
            self.sell_size = sell_size
            self.total_size = buy_size + sell_size
            self.buy_sell_size_ratio = buy_size / sell_size if sell_size > 0 else MAX_INTEGER

            self.buy_count = buy_count
            self.sell_count = sell_count
            self.total_count = buy_count + sell_count
            self.buy_sell_count_ratio = buy_count / sell_count if sell_count > 0 else MAX_INTEGER
            
            self.logger.info("%d-%d-%d-%f|-%d-%d-%d-%f|%d-%f-%f|%f-%f"%(
                self.total_size,
                self.buy_size,
                self.sell_size,
                self.buy_sell_size_ratio,
                self.total_count,
                self.buy_count,
                self.sell_count,
                self.buy_sell_count_ratio,
                self.last_price,
                self.price_change,
                self.price_change_rate,
                self.high,
                self.low
                )
            )
            #self.logger.info(self.prices)
            #self.logger.info(self.price_change)

            sleep(1)
    # 是否在瀑布，短时间内下跌超过1%
    def is_jump(self):
        return self.price_change_rate <= -1.0/100

    if __name__ == "__main__":
        print("HELLO")
