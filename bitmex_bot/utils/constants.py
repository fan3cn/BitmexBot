import subprocess
# Constants
XBt_TO_XBT = 100000000
VERSION = 'v1.1'
try:
    VERSION = str(subprocess.check_output(["git", "describe", "--tags"]).rstrip())
except Exception as e:
    # git not available, ignore
    pass
# 账户内的初始余额
INITIAL_BALANCE = 0.015
# 账户余额小于一半时，停止程序
STOP_BALANCE_RATIO = 0.5