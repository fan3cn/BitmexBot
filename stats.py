import logging
from collections import deque

class Stats():
    def __init__(self, ws):
        self.logger = logging.getLogger('root')
        self.ws = ws
        self.trades = ws.recent_trades()
        # keep last 30 trades price
        self.last_prices = deque(maxlen=30)
        self.buy_sell_ratio = 1.0
    def __del__(self):
        self.exit()

    def exit(self):
        self.exited = True

    def run(self):
        self.logger.info("Stats running...")
        # calculate on real-time trade data every SEC.
        while (self.ws.sock.connected):
            trades = self.trades
            buy_size, sell_size, buy_count, sell_count = 0
            for trade in trades:
                if trade['side'] == "Buy":
                    buy_size += trade['size']
                    buy_count += 1
                else:
                    sell_size += trade['size']
                    sell_count += 1
                self.last_prices.append(trade['price'])

            self.buy_sell_ratio = buy_size / sell_size if sell_size > 0 else 100000

            self.logger.info("%d-%d-%f-%d-%d"%(buy_size, sell_size, self.buy_sell_ratio, buy_count, sell_count))
            sleep(1)

    if __name__ == "__main__":
        print("HELLO")