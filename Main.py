import configparser
import sched
import time
import threading
from datetime import datetime
from sys import platform

from ApiWrapper import IBapi, createContract, createTrailingStopOrder, createLMTbuyorder
from DataBase.db import updateOpenPostionsInDB, updateOpenOrdersinDB, dropPositions, dropOpenOrders, dropCandidates, \
    updateCandidatesInDB, GetAverageDropForStock, checkDB, updateTipRanksInDB, GetRanksForStocks
from pytz import timezone

from Research.UpdateCandidates import updatetMarketStatisticsForCandidates
from Research.tipRanksScrapper import getStocksData

config = configparser.ConfigParser()
config.read('config.ini')
PORT = config['Connection']['portp']
ACCOUNT = config['Account']['accp']
INTERVAL = config['Connection']['interval']

MACPATHTOWEBDRIVER = config['Connection']['macPathToWebdriver']
if platform == "linux" or platform == "linux2":
    PATHTOWEBDRIVER = config['Connection']['macPathToWebdriver']
elif platform == "darwin":#mac os
    PATHTOWEBDRIVER = config['Connection']['macPathToWebdriver']
elif platform == "win32":
    PATHTOWEBDRIVER = config['Connection']['winPathToWebdriver']
# alg
PROFIT = config['Algo']['gainP']
TRAIL = config['Algo']['trailstepP']
BULCKAMOUNT = config['Algo']['bulkAmountUSD']
TRANDINGSTOCKS = ["AAPL", "FB", "ZG", "MSFT", "NVDA", "TSLA", "BEP", "GOOGL","ETSY"]


def init_candidates():
    # starting querry
    for s in TRANDINGSTOCKS:
        id = app.nextorderId
        print("starting to track: ", s, "traking with Id:", id)
        c = createContract(s)
        app.candidates[id] = {"Stock": s,
                              "Close": "-",
                              "Bid": "-",
                              "Ask": "-",
                              "LastPrice": "-",
                              "LastUpdate": "-"}
        app.reqMarketDataType(1)
        app.reqMktData(id, c, '', False, False, [])
        app.nextorderId += 1
        time.sleep(0.5)

    updatetMarketStatisticsForCandidates(TRANDINGSTOCKS)


def processProfits():
    print("Processing profits")
    for i, p in app.positionDetails.items():
        if p["Value"] == 0:
            continue
        profit = p["UnrealizedPnL"] / p["Value"] * 100
        if profit > float(PROFIT):
            orders = app.openOrders
            if p["Stock"] in orders:
                print("Order for ", p["Stock"], "already exist- skipping")
            else:
                print("Profit for: ", p["Stock"], " is ", profit, "Creating a trailing Stop Order")
                contract = createContract(p["Stock"])
                order = createTrailingStopOrder(p["Position"], TRAIL)
                app.placeOrder(app.nextorderId, contract, order)
                app.nextorderId = app.nextorderId + 1
                print("Created a Trailing Stop order for ", p["Stock"], " at level of ", TRAIL, "%")


def evaluateBuy(s):
    print("evaluating ",s,"for a Buy")

    for c in app.candidates.values():
        if c["Stock"]==s:
            ask_price=c["Ask"]
            last_closing=c["Close"]
            break
    average_daily_dropP=GetAverageDropForStock(s)

    target_price=last_closing-last_closing/100*average_daily_dropP

    ranks=GetRanksForStocks()
    tipRank=ranks[s]["tipranks"]

    if ask_price==-1:#market is closed
        pass
    elif ask_price>target_price and tipRank<8:
        print(s,"is too expensive waiting for lower than ",target_price,"to exceed average ",average_daily_dropP," %")
    else:
        buyTheStock(ask_price, s)

    pass


def buyTheStock(ask_price, s):
    contract = createContract(s)
    stocksToBuy=int(int(BULCKAMOUNT)/ask_price)
    if stocksToBuy>0:
        print("Issued the BUY order at ", ask_price,"for ",stocksToBuy," Stocks of ",s)
        order = createLMTbuyorder(stocksToBuy, ask_price)
        app.placeOrder(app.nextorderId, contract, order)
        app.nextorderId = app.nextorderId + 1
    else:
        print("The single stock is too expensive - skipping")


def processCandidates():

    excessLiquidity=app.excessLiquidity
    if float(excessLiquidity)<1000:
        return
    else:
        print("The Excess liquidity is :",excessLiquidity," searching candidates")
        for s in TRANDINGSTOCKS:
            if s in app.openPositions:
                continue
            else:
                evaluateBuy(s)


s = sched.scheduler(time.time, time.sleep)


def workerGo(sc):
    est = timezone('EST')
    fmt = '%Y-%m-%d %H:%M:%S'
    time = datetime.now(est).strftime(fmt)

    print("---------------Processing Worker...-------EST Time: ", time, "--------------------")
    # collect and update
    updateOrders()
    updatePositions()
    updateCandidates()

    # process
    processCandidates()
    processProfits()
    print("...............Worker finished.........................")

    s.enter(float(INTERVAL), 1, workerGo, (sc,))


def run_loop():
    app.run()


def updatePositions():
    dropPositions()
    updateOpenPostionsInDB(app.positionDetails)
    print(len(app.positionDetails), " positions info updated")


def updateCandidates():
    dropCandidates()
    updateCandidatesInDB(app.candidates)
    print(len(app.candidates), " candidates info updated")


def get_positions():
    # update positions from IBKR
    print("Updating positions:")
    app.reqPositions()  # requesting complete list
    time.sleep(1)
    for s, p in app.openPositions.items():  # start tracking one by one
        id = app.nextorderId
        app.positionDetails[id] = {"Stock": s}
        app.reqPnLSingle(id, ACCOUNT, "", p["conId"])  # requesting one by one
        app.nextorderId += 1

    time.sleep(2)
    updatePositions()


def updateOrders():
    print("Updating all open Orders")
    app.openOrders = {}
    app.reqAllOpenOrders()
    time.sleep(1)
    dropOpenOrders()
    updateOpenOrdersinDB(app.openOrders)
    print(len(app.openOrders), " Orders found and saved to DB")


print("Starting Todays session:", time.ctime())
#check if DB is missing- if yes- create
checkDB()
#update TipranksData
print("Updating a ratings for Candidate stocks...")
updateTipRanksInDB(getStocksData(TRANDINGSTOCKS,PATHTOWEBDRIVER))
app = IBapi()
app.connect('127.0.0.1', int(PORT), 123)
app.nextorderId = None
# Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()
print("Started waiting for connection")
# Check if the API is connected via orderid
while True:
    if isinstance(app.nextorderId, int):
        print('connected')
        break
    else:
        print('waiting for connection')
        time.sleep(1)

id = app.nextorderId

# General Account info:
app.reqPnL(id, ACCOUNT, "")
app.nextorderId = app.nextorderId + 1
id = app.nextorderId
app.reqAccountSummary(id, "All", "ExcessLiquidity")
app.nextorderId += 1
time.sleep(0.5)
status = app.generalStatus
print("PnL today status: ")
print(status)

# start tracking open positions
get_positions()

# start tracking candidates
init_candidates()


print("**********************Connected, Ready!!! starting Worker********************")
# starting worker in loop...
s.enter(2, 1, workerGo, (s,))
s.run()
