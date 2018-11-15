import datetime


def last_5mins():
    mins = datetime.datetime.now().minute
    return mins - mins % 5