from datetime import datetime
import traceback, sys
import configparser
from sys import platform

from PySide2.QtCore import QRunnable, Slot, QThreadPool, Signal, QObject, QTimer
from PySide2.QtGui import QColor, QTextCursor
from PySide2.QtUiTools import loadUiType
from PySide2.QtWidgets import QMainWindow, QApplication, QTableWidgetItem, QWidget

from Logic.IBKRWorker import IBKRWorker

# The bid price refers to the highest price a buyer will pay for a security.
# The ask price refers to the lowest price a seller will accept for a security.

main_window_file = "UI/MainWindow.ui"
settings_window_file = "UI/SettingsWindow.ui"
Ui_MainWindow, MainBaseClass = loadUiType(main_window_file)
Ui_SettingsWindow, SettingsBaseClass = loadUiType(settings_window_file)
LOGFILE = "log.txt"


class OutLog:
    def __init__(self, edit, out=None, color=None):
        """(edit, out=None, color=None) -> can redirect Console output to a
        QTextEdit.
        edit = QTextEdit
        out = alternate stream ( can be the original sys.stdout )
        color = alternate color (i.e. color stderr a different color)
        """
        self.edit = edit
        self.out = out
        self.color = color
        self.logLine = ""

    def write(self, m):
        """
writes text to Qedit
        :param m: text to write
        """
        try:
            if self.color:
                tc = self.edit.textColor()
                self.edit.setTextColor(self.color)

            # self.edit.moveCursor(QTextCursor.End)
            # self.edit.insertPlainText(m)
            # self.log_message(m)
            self.logLine += m

            if self.color:
                self.edit.setTextColor(tc)

            if self.out:
                self.out.write(m)
        except:
            print("OUTERRORHAPPENED")

    def flush(self):
        """
required to avoid error
        """
        r = 3

    def flush_to_log_file(self, m):
        """
adds portion to the log file
        :param m:
        """
        with open(LOGFILE, "a") as f:
            currentDt = datetime.now().strftime("%d-%b-%Y (%H:%M:%S.%f)")
            m = currentDt + '---' + m
            f.write(m)


class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        `tuple` (exctype, value, traceback.format_exc() )

    result
        `object` data returned from processing, anything

    '''
    finished = Signal()  # QtCore.Signal
    error = Signal(tuple)
    result = Signal(object)
    status = Signal(object)


class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()  # QtCore.Slot
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(
                *self.args, **self.kwargs
            )
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class TraderSettings():
    def __init__(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        self.PORT = config['Connection']['portp']
        self.ACCOUNT = config['Account']['accp']
        self.INTERVAL = config['Connection']['interval']

        if platform == "linux" or platform == "linux2":
            self.PATHTOWEBDRIVER = config['Connection']['macPathToWebdriver']
        elif platform == "darwin":  # mac os
            self.PATHTOWEBDRIVER = config['Connection']['macPathToWebdriver']
        elif platform == "win32":
            self.PATHTOWEBDRIVER = config['Connection']['winPathToWebdriver']
        # alg
        self.PROFIT = config['Algo']['gainP']
        self.LOSS = config['Algo']['lossP']
        self.TRAIL = config['Algo']['trailstepP']
        self.BULCKAMOUNT = config['Algo']['bulkAmountUSD']
        self.TRANDINGSTOCKS = ["AAPL", "FB", "ZG", "MSFT", "NVDA", "TSLA", "BEP", "GOOGL", "ETSY", "IVAC"]
        # self.TRANDINGSTOCKS = ["AAPL"]


class MainWindow(MainBaseClass, Ui_MainWindow):
    def __init__(self):
        # mandatory
        QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.settings = TraderSettings()
        self.ibkrworker = IBKRWorker(self.settings)
        self.threadpool = QThreadPool()

        # redirecting Cosole to UI and Log
        sys.stdout = OutLog(self.consoleOut, sys.stdout)
        sys.stderr = OutLog(self.consoleOut, sys.stderr)

        # setting a timer for Worker
        self.timer = QTimer()
        self.timer.timeout.connect(self.run_worker)

        # connecting a buttons
        self.btnConnect.pressed.connect(self.connect_to_ibkr)
        self.btnStart.pressed.connect(self.start_timer)
        self.btnSettings.pressed.connect(self.show_settings)

        self.statusbar.showMessage("Ready")
        print("AlgoTraider is started... waiting to connect...")

    def connect_to_ibkr(self):
        """
Starts the connection to the IBKR terminal in separate thread
        """

        self.btnConnect.setEnabled(False)

        connector = Worker(self.ibkrworker.connect_and_prepare)  # Any other args, kwargs are passed to the run function
        connector.signals.result.connect(self.update_ui)
        connector.signals.finished.connect(self.thread_complete)
        # Execute
        self.threadpool.start(connector)
        self.btnStart.setEnabled(True)
        self.statusbar.showMessage("Started Connect")

    def start_timer(self):
        """
Starts the Timer with interval from Config file
        """
        self.timer.start(int(self.settings.INTERVAL) * 1000)

    def run_worker(self):
        """
Executed the Worker in separate thread
        """
        worker = Worker(
            self.ibkrworker.process_positions_candidates)  # Any other args, kwargs are passed to the run function
        worker.signals.result.connect(self.update_ui)
        worker.signals.finished.connect(self.thread_complete)
        # Execute
        self.threadpool.start(worker)
        self.statusbar.showMessage("Executing Worker")

    def update_ui(self, s):
        """
Updates UI after connection/worker execution
        :param s:
        """
        self.lLiq.setText(self.ibkrworker.app.excessLiquidity)
        self.lAcc.setText(self.settings.ACCOUNT)
        self.update_open_positions()
        self.update_live_candidates()
        self.update_open_orders()

        self.statusbar.showMessage(s)
        self.update_console()

    def update_console(self):
        # errors part
        log = sys.stderr.logLine
        self.consoleOut.append(log)
        sys.stderr.flush_to_log_file(log)
        sys.stderr.logLine = ""

        # messages part
        log = sys.stdout.logLine
        self.consoleOut.append(log)
        sys.stdout.flush_to_log_file(log)
        sys.stdout.logLine = ""

    def update_live_candidates(self):
        """
Updates Candidates table
        """
        liveCandidates = self.ibkrworker.app.candidatesLive
        try:
            line = 0
            self.tCandidates.setRowCount(len(liveCandidates))
            for k, v in liveCandidates.items():
                self.tCandidates.setItem(line, 0, QTableWidgetItem(v['Stock']))
                self.tCandidates.setItem(line, 1, QTableWidgetItem(str(v['Open'])))
                self.tCandidates.setItem(line, 2, QTableWidgetItem(str(v['Close'])))
                self.tCandidates.setItem(line, 3, QTableWidgetItem(str(v['Bid'])))
                self.tCandidates.setItem(line, 4, QTableWidgetItem(str(v['Ask'])))
                self.tCandidates.setItem(line, 5, QTableWidgetItem(str(v['LastPrice'])))
                self.tCandidates.setItem(line, 6, QTableWidgetItem(str(round(v['target_price'], 2))))
                self.tCandidates.setItem(line, 7, QTableWidgetItem(str(round(v['averagePriceDropP'], 2))))
                self.tCandidates.setItem(line, 8, QTableWidgetItem(str(v['tipranksRank'])))
                self.tCandidates.setItem(line, 9, QTableWidgetItem(str(v['LastUpdate'])))

                line += 1
        except Exception as e:
            print("Error loading Candidates table: ", str(e))

    def update_open_positions(self):
        """
Updates Positions table
        """
        openPostions = self.ibkrworker.app.openPositions
        try:
            line = 0
            self.tPositions.setRowCount(len(openPostions))
            for k, v in openPostions.items():
                self.tPositions.setItem(line, 0, QTableWidgetItem(k))
                self.tPositions.setItem(line, 1, QTableWidgetItem(str(int(v['stocks']))))
                self.tPositions.setItem(line, 2, QTableWidgetItem(str(round(v['cost'], 2))))
                self.tPositions.setItem(line, 3, QTableWidgetItem(str(round(v['Value'], 2))))
                self.tPositions.setItem(line, 4, QTableWidgetItem(str(round(v['UnrealizedPnL'], 2))))

                profit = v['UnrealizedPnL'] / v['Value'] * 100
                self.tPositions.setItem(line, 5, QTableWidgetItem(str(round(profit, 2))))

                if v['UnrealizedPnL'] > 0:
                    self.tPositions.item(line, 4).setBackgroundColor(QColor(51, 204, 51))
                    self.tPositions.item(line, 5).setBackgroundColor(QColor(51, 204, 51))
                else:
                    self.tPositions.item(line, 4).setBackgroundColor(QColor(255, 51, 0))
                    self.tPositions.item(line, 5).setBackgroundColor(QColor(255, 51, 0))
                line += 1
        except Exception as e:
            print("Error loading Open Positions table: ", str(e))

    def update_open_orders(self):
        """
Updates Positions table
        """
        openOrders = self.ibkrworker.app.openOrders
        try:
            line = 0
            self.tOrders.setRowCount(len(openOrders))
            for k, v in openOrders.items():
                self.tOrders.setItem(line, 0, QTableWidgetItem(k))
                self.tOrders.setItem(line, 1, QTableWidgetItem(v['Action']))
                self.tOrders.setItem(line, 2, QTableWidgetItem(v['Type']))
                line += 1
        except Exception as e:
            print("Error loading Orders table: ", str(e))

    def thread_complete(self):
        """
After threaded task finished
        """
        print("TASK COMPLETE!")

    def show_settings(self):
        settingsW.show()


class SettingsWindow(SettingsBaseClass, Ui_SettingsWindow):
    def __init__(self):
        # mandatory
        SettingsBaseClass.__init__(self)
        Ui_SettingsWindow.__init__(self)
        self.setupUi(self)


app = QApplication(sys.argv)
window = MainWindow()
settingsW = SettingsWindow()
window.show()
sys.exit(app.exec_())
