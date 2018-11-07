import logging
from collections import deque
from time import sleep

class Stats():
    def __init__(self, ws):
        self.logger = logging.getLogger('Stats')
        self.ws = ws
        #self.trades = ws.recent_trades()
        # keep last 60 second trade price
        self.last_prices = deque(maxlen=60)
        self.buy_sell_ratio = 1.0
        #self.last_price = 0.0
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

            self.last_prices.append(self.last_price)
            self.price_change_60_secs = self.last_price - self.last_prices[0]

            self.buy_sell_size_ratio = buy_size / sell_size if sell_size > 0 else 100000
            self.buy_sell_count_ratio = buy_count / sell_count if sell_count > 0 else 100000 
            
            self.logger.info("%d-%d-%f-%d-%d-%f"%(buy_size, sell_size, self.buy_sell_size_ratio, buy_count, sell_count, self.buy_sell_count_ratio))
            self.logger.info(self.last_prices)
            self.logger.info(self.price_change_60_secs)

            sleep(1)


    if __name__ == "__main__":
        print("HELLO")
