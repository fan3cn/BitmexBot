import requests
import json
import settings as s


class Bitmex(object):

    def __init__(self):
        self.trade_currency = "XBT"
        self.ask_price = 0
        self.bid_price = 0
        self.order_id_prefix = "lee_bot"
        self.symbol = s.SYMBOL
        self.BASE_URL = s.BASE_URL_TESTING if s.MODE == "TESTING" else s.BASE_URL_LIVE
            #"https://www.bitmex.com/api/v1/"

    def get_historical_data(self, tick='5m', count=400, reverse="false", partial="false",
                            start_time='', end_time=''):
        # last one hour data with latest one in the end

        url = self.BASE_URL + "trade/bucketed?binSize={}&partial={}&symbol={}&count={}&reverse={}" \
                              "&startTime={}&endTime={}". \
            format(tick, partial, self.symbol, count, reverse, start_time, end_time)
        r = json.loads(requests.get(url).text)

        lst = []
        # configure result into suitable data type
        try:
            dict_key = ["open", "close", "high", "low", "volume", "vwap", "timestamp"]
            for item in r:
                d = {
                    dict_key[0]: item[dict_key[0]],
                    dict_key[1]: item[dict_key[1]],
                    dict_key[2]: item[dict_key[2]],
                    dict_key[3]: item[dict_key[3]],
                    dict_key[4]: item[dict_key[4]],
                    dict_key[5]: item[dict_key[5]],
                    dict_key[6]: item[dict_key[6]]
                }
                lst.append(d)
            return lst
        except KeyError as e:
            pass
        except TypeError as e:
            pass
        except Exception as e:
            pass

