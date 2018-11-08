import logging
from time import sleep
from bitmex_bot.bitmex_historical import Bitmex

class HistoricalStats():

    def __init__(self):
        self.logger = logging.getLogger('RealtimeStats')
        self.trades_1_mins = []
        self.trades_3_mins = []
        self.trades_5_mins = []
        self.trades_10_mins = []
        self.trades_15_mins = []


    def run(self):
        self.logger.info("HistoricalStats running...")
        while(True):

            lst = Bitmex().get_historical_data()
            print(lst)
            sleep(1)




    if __name__ == "__main__":
        print("HELLO")