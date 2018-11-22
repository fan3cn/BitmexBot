import logging
import datetime
from time import sleep
from bitmex_bot.bitmex_historical import Bitmex
from bitmex_bot.utils.util import last_5mins
from bitmex_bot.utils import constants
import settings
import bitmex_bot.utils.constants


class Policy():

    def __init__(self):
        self.logger = logging.getLogger()
        # keep Six hours(60min * 6 = 360) data
        self.trades_1_min = []
        # keep One day(24hour*60/5 = 288) data
        self.trades_5_min = []
        # Keep the latest trades with bin size of 5 min
        self.trades_5_min_partial = []
        #self.trades_5_min = []
        #self.trades_15_min = []
        # keep 5 days(5*24=120) data
        self.trades_1_hour = []
        # keep 30 days data
        self.trades_1_day = []

        self.last_exe_time = -1
        self.last_exe_time_log = -1

    def fetch_historical_data(self):
        if last_5mins() != self.last_exe_time:
            self.trades_5_min = Bitmex().get_historical_data(tick='5m', count=10, reverse='true', partial='true')
            self.trades_5_min = self.trades_5_min[1:6]
            self.trades_5_min_partial = self.trades_5_min[0:1]
            self.logger.info(self.trades_5_min)
            self.last_exe_time = last_5mins()

    def run(self):
        self.logger.info("Policy running...")
        while(True):

            #self.trades_1_min = Bitmex().get_historical_data(count=360)
            #print(self.trades_1_min)

            self.trades_5_min = Bitmex().get_historical_data(tick='5m', count=6)
            #print(self.trades_5_min)

            # self.trades_1_hour = Bitmex().get_historical_data(tick='1h', count=120)
            # print(self.trades_1_hour)
            #
            # self.trades_1_day = Bitmex().get_historical_data(tick='1d', count=30)
            # print(self.trades_1_day)
            #self.trade_signal()

            sleep(120)

    def down(self, trade):
        return  self.open(trade) > self.close(trade)

    def up(self, trade):
        return  self.open(trade) <= self.close(trade)

    def trade_gap(self, trade):
        return abs(self.close(trade) - self.open(trade))

    def trade_volume(self, trade):
        return float(trade['volume'])

    def trade_volume_ratio(self, trade, p_trade):
        if self.trade_volume(p_trade) <= 0:
            return 0
        return self.trade_volume(trade) / self.trade_volume(p_trade)

    def open(self, trade):
        return float(trade['open'])

    def close(self, trade):
        return float(trade['close'])

    def avg(self, trade):
        return (float(trade['open']) + float(trade['close']) )/2

    # 连续两个五分钟：
    #     # 上涨时：volume > 2M and gap >= 0.3 and volume_ratio > 5
    #     # 下跌时：volume > 1M and gap >= 0.3 and volume_ratio > 5
    #     # 放量上涨 / 下跌->多、空
    def rule_1(self):
        # current trade
        trade = self.trades_5_min[0]
        # previous trade
        p_trade = self.trades_5_min[1]

        if self.down(p_trade) and self.down(trade) and \
                self.trade_volume(trade) >= settings.RULE_1_DOWN_VOLUME and \
                self.trade_volume_ratio(trade, p_trade) >= settings.RULE_1_DOWN_VOLUME_RATIO and \
                self.trade_gap(trade) >= settings.RULE_1_DOWN_TRADE_GAP:

            self.logger.info("SIGNAL DOWN, Policy rule_1 hits, trade volume:{},trade_volume_ratio:{}, trade gap:{}, from {} to {}." \
                             .format(self.trade_volume(trade), self.trade_volume_ratio(trade, p_trade), \
                    self.trade_gap(trade), self.open(trade), self.close(trade)))

            return constants.DOWN

        if self.up(p_trade) and self.up(trade) and \
                self.trade_volume(trade) >= settings.RULE_1_UP_VOLUME and \
                self.trade_volume_ratio(trade, p_trade) >= settings.RULE_1_UP_VOLUME_RATIO and \
                self.trade_gap(trade) >= settings.RULE_1_UP_TRADE_GAP:

            self.logger.info("SIGNAL UP, Policy rule_1 hits, trade volume:{},trade_volume_ratio:{}, trade gap:{}, from {} to {}." \
                             .format(self.trade_volume(trade), self.trade_volume_ratio(trade, p_trade), \
                    self.trade_gap(trade), self.open(trade), self.close(trade)))

            return constants.UP

        return constants.FLAT

    # 连续三个五分钟：持续下跌，量级递增，且有一个gap大于0.3
    def rule_2(self):
        trade = self.trades_5_min[0]
        p_trade = self.trades_5_min[1]
        pp_trade = self.trades_5_min[2]

        is_all_down = self.down(trade) and self.down(p_trade) and self.down(pp_trade)
        is_volume_up = self.trade_volume(trade) >= self.trade_volume(p_trade) and \
                         self.trade_volume(p_trade)>= self.trade_volume(pp_trade)
        has_one_dump = self.trade_gap(trade) >= settings.RULE_2_DOWN_TRADE_GAP or \
                       self.trade_gap(p_trade) >= settings.RULE_2_DOWN_TRADE_GAP or \
                       self.trade_gap(pp_trade) >= settings.RULE_2_DOWN_TRADE_GAP

        if is_all_down and is_volume_up and has_one_dump:

            self.logger.info("SIGNAL DOWN, Policy rule_2 hits, trade volumes:{}-{}-{}," \
                             "trade_gaps:{}-{}-{}" \
                             .format(
                self.trade_volume(trade), self.trade_volume(p_trade), self.trade_volume(pp_trade), \
                self.trade_gap(trade), self.trade_gap(p_trade), self.trade_gap(pp_trade))
            )

            return constants.DOWN

        is_all_up = self.up(trade) and self.up(p_trade) and self.up(pp_trade)
        has_one_jump = self.trade_gap(trade) >= settings.RULE_2_UP_TRADE_GAP or \
                       self.trade_gap(p_trade) >= settings.RULE_2_UP_TRADE_GAP or \
                       self.trade_gap(pp_trade) >= settings.RULE_2_UP_TRADE_GAP

        if is_all_up and is_volume_up and has_one_jump:


            self.logger.info("SIGNAL UP, Policy rule_2 hits, trade volumes:{}-{}-{}," \
                             "trade_gaps:{}-{}-{}" \
                             .format(
                self.trade_volume(trade), self.trade_volume(p_trade), self.trade_volume(pp_trade), \
                self.trade_gap(trade), self.trade_gap(p_trade), self.trade_gap(pp_trade))
            )


            return constants.UP

        return constants.FLAT

    # 连续五个五分钟：
    # 持续上涨，close - open > 0
    # 持续下跌，close - open < 0
    def rule_3(self):
        unit = settings.RULE_3_CONSECUTIVE_UP
        trades = self.trades_5_min[0:unit:1][::-1]
        head_tail_gap = abs(self.avg(trades[0]) - self.avg(trades[-1]))

        if sum([self.up(trade) for trade in trades]) >= unit and \
            head_tail_gap >= settings.RULE_3_HEAD_TAIL_GAP_UP:

            self.logger.info("SIGNAL UP, Policy rule_3 hits, head tail gap {}.".format(head_tail_gap))

            return constants.UP

        unit = settings.RULE_3_CONSECUTIVE_DOWN
        trades = self.trades_5_min[0:unit:1][::-1]
        head_tail_gap = abs(self.avg(trades[0]) - self.avg(trades[-1]))

        if sum([self.down(trade) for trade in trades]) >= unit and \
            head_tail_gap >= settings.RULE_3_HEAD_TAIL_GAP_DOWN:

            self.logger.info("SIGNAL DOWN, Policy rule_3 hits, head tail gap {}.".format(head_tail_gap))

            return constants.DOWN

        return constants.FLAT

    # 短时间内放量下跌/上涨
    def rule_4(self):
        trade = self.trades_5_min_partial[0]
        if self.up(trade) and \
                self.trade_gap(trade) >= settings.RULE_4_SURGE_TRADE_GAP and \
                self.trade_volume(trade) >= settings.RULE_4_SURGE_VOLUME:
            self.logger.info("SIGNAL UP, Market surges, Policy rule_4 hits, surge gap:{}, trade volume:{}." \
                             .format(self.trade_gap(trade), self.trade_volume(trade)))
            return constants.UP

        if self.down(trade) and \
                self.trade_gap(trade) >= settings.RULE_4_PLUNGE_TRADE_GAP and \
                self.trade_volume(trade) >= settings.RULE_4_PLUNGE_VOLUME:
            self.logger.info("SIGNAL DOWN, Market surges, Policy rule_4 hits, surge gap:{}, trade volume:{}." \
                             .format(self.trade_gap(trade), self.trade_volume(trade)))
            return constants.DOWN

        return constants.FLAT

    # 连续4个5分钟平均价格下跌/上涨
    def rule_5(self):
        unit = settings.RULE_5_CONSECUTIVE_UP
        trades = self.trades_5_min[0:unit:1][::-1]
        head_tail_gap = abs(self.avg(trades[0]) - self.avg(trades[-1]))
        pre_avg = -1
        count = 0
        for trade in trades:
            if self.avg(trade) >= pre_avg:
                count += 1
            pre_avg = self.avg(trade)

        if count >= unit and \
            head_tail_gap >= settings.RULE_5_HEAD_TAIL_GAP_UP:

            self.logger.info("SIGNAL UP, Policy rule_5 hits, head tail gap {}.".format(head_tail_gap))

            return constants.UP

        unit = settings.RULE_5_CONSECUTIVE_DOWN
        trades = self.trades_5_min[0:unit:1][::-1]
        head_tail_gap = abs(self.avg(trades[0]) - self.avg(trades[-1]))

        pre_avg = settings.ONE_MILLION
        count = 0
        for trade in trades:
            if self.avg(trade) <= pre_avg:
                count += 1
            pre_avg = self.avg(trade)

        if count >= unit and \
            head_tail_gap >= settings.RULE_5_HEAD_TAIL_GAP_DOWN:

            self.logger.info("SIGNAL DOWN, Policy rule_5 hits, head tail gap {}.".format(head_tail_gap))

            return constants.DOWN

        return constants.FLAT



    def trade_signal(self):
        signal = self._trade_signal()

        if settings.TEST_SIGNAL and settings.MODE == "TESTING":
            return settings.TEST_SIGNAL

        return signal

    def _trade_signal(self):

        self.format_OHLC_log(self.trades_5_min[0])
        
        r4 = self.rule_4()
        if r4 > constants.FLAT:
            return r4
        
        r1 = self.rule_1()
        if r1 > constants.FLAT:
            return r1
        
        r2 = self.rule_2()
        if r2 > constants.FLAT:
            return r2
        
        r3 = self.rule_3()
        if r3 > constants.FLAT:
            return r3
        
        return constants.FLAT

    # RealTime trade signal
    def current_trade_signal(self):
        trade = self.trades_5_min_partial[0]
        if self.up(trade):
            return constants.UP
        elif self.down(trade):
            return constants.DOWN
        else:
            return constants.FLAT

    def format_OHLC_log(self, trade):
        if last_5mins() == self.last_exe_time_log:
            return
        UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
        UTC_TIME = datetime.datetime.strptime(trade['timestamp'], UTC_FORMAT)
        localtime = UTC_TIME + datetime.timedelta(hours=8)

        self.logger.info("Open:{}, High:{}, Low:{}, Close:{}, Volume:{}, ts:{}" \
                         .format(self.open(trade), trade['high'], trade['low'], self.close(trade),
                                 self.trade_volume(trade), localtime))
        self.last_exe_time_log = last_5mins()
    # 使用历史数据测试
    def simulate(self):
        self.logger.info("Policy test running...")

        # start from 8/4 to 11/1
        UTC_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
        start_time = datetime.datetime.strptime('2018-08-04T00:00:00.000Z', UTC_FORMAT)

        # 1000美元
        self.balance = 1000
        self.leverage = 50
        self.fee_ratio = 0.00075
        self.contract_num = self.balance * self.leverage * 0.5
        self.fee = self.contract_num * self.fee_ratio
        #self.contract_num = 3000
        #self.leverage = 50

        self.is_in_trade = False
        self.profit_price = 0
        self.stop_price = 0
        self.eth_num = 0
        self.position = 0
        self.margin = 0

        for d in range(4 * 30):
            end_time =start_time + datetime.timedelta(days=1)
            print("{}-{}".format(start_time, end_time))
            trades_5_min = Bitmex().get_historical_data(start_time=start_time, end_time=end_time)
            #print(trades_5_min)
            i = 0
            j = 5

            if self.balance <= 0:
                self.logger.info("Congratulations, you go bankrupt ^v^")
                break

            while (j < len(trades_5_min)):
                self.trades_5_min = trades_5_min[i:j][::-1]
                close = float(self.trades_5_min[0]['close'])
                open = float(self.trades_5_min[0]['open'])

                if self.balance <= 0:
                    self.logger.info("Congratulations, you go bankrupt ^v^")
                    break

                #start = open if open <= close else close
                #end = close if open > close else open

                price = (open + close)/2

                if self.is_in_trade:
                    #持单中，检查止盈止损
                    if self.position > 0:
                        # 多单，卖出止盈、止损
                        if price >= self.profit_price or price <= self.stop_price:
                            profit = self.eth_num * price - self.contract_num
                            self.position = self.position - self.contract_num

                            self.margin = self.margin + profit
                            self.balance = self.balance + self.margin - self.fee

                            if price >= self.profit_price:
                                self.logger.info("Take profit at price:{}, ETH num:{}, balance:{}, position:{}"
                                                 .format(price, self.eth_num, self.balance, self.position))

                            if price <= self.stop_price:
                                self.logger.info("Stop loss at price:{}, ETH num:{}, balance:{}, position:{}"
                                                 .format(price, self.eth_num, self.balance, self.position))

                            self.reset()
                    else:
                        # 空单，买入止盈、止损
                        if price <= self.profit_price or price >= self.stop_price:
                            profit = self.contract_num - self.eth_num * price
                            self.position = self.position + self.contract_num

                            self.margin = self.margin + profit
                            self.balance = self.balance + self.margin - self.fee

                            if price <= self.profit_price:
                                self.logger.info("Take profit at price:{}, ETH num:{}, balance:{}, position:{}"
                                                 .format(price, self.eth_num, self.balance, self.position))

                            if price >= self.stop_price:
                                self.logger.info("Stop loss at price:{}, ETH num:{}, balance:{}, position:{}"
                                                 .format(price, self.eth_num, self.balance, self.position))

                            self.reset()
                else:
                    signal = self.trade_signal()

                    if signal == constants.UP:
                        # 买入，place order
                        buy_price = price
                        self.margin = self.contract_num / self.leverage
                        self.balance = self.balance - self.margin - self.fee
                        self.eth_num = self.contract_num / buy_price

                        # 20倍杠杆，买入1000美元的合约，成本50刀
                        self.profit_price = buy_price + 2
                        self.stop_price = buy_price - 0.5
                        self.is_in_trade = True
                        self.position = self.position + self.contract_num
                        self.logger.info("Long ETH at price:{}, ETH num:{}, profit price:{}, stop price:{}, balance:{}, position:{}"
                                         .format(buy_price, self.eth_num, self.profit_price, self.stop_price, self.balance, self.position))
                    elif signal == constants.DOWN:
                        # 卖出，place order
                        sell_price = price
                        self.margin = self.contract_num / self.leverage
                        self.balance = self.balance - self.margin - self.fee
                        self.eth_num = self.contract_num / sell_price

                        # 20倍杠杆，买入1000美元的合约，成本50刀
                        self.profit_price = sell_price - 2.5
                        self.stop_price = sell_price + 0.5
                        self.is_in_trade = True
                        self.position = self.position - self.contract_num
                        self.logger.info("Short ETH at price:{}, ETH num:{}, profit price:{}, stop price:{}, balance:{}, position:{}"
                                         .format(sell_price, self.eth_num, self.profit_price, self.stop_price, self.balance, self.position))

                #self.logger.info("BALANCE:{}".format(self.balance))

                i += 1
                j += 1

                #sleep(1)

            start_time = end_time

    def reset(self):
        self.is_in_trade = False
        self.profit_price = 0
        self.stop_price = 0
        self.eth_num = 0
        self.margin = 0
    
if __name__ == "__main__":
    #print("Policy starts....")
    # create console handler and set level to debug
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    # create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # add formatter to ch
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    fh = logging.FileHandler('test.log')
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    p = Policy()
    p.logger = logger
    p.simulate()

