from abc import ABC, abstractmethod
from queue import Queue
import signal
import os
import json
import time
import calendar
import threading
#import client_config
#import c_log
import logging

logger = logging.getLogger(__name__)

class abstractServer(ABC):
    def __init__(self, timer_lapse=200):
        super().__init__()
        self.queue = Queue()
        self.timer_lapse = timer_lapse
        self.time_thread = threading.Timer(self.timer_lapse, self.on_timeout)
        #signal.signal(signal.SIGINT, self.handler)

    def put_msg(self, msg):
        # Multiple reading in single message
        #for m in msg:
        #    self.devices[m["nodeId"]].update()
        #try:
        #    n = json.dumps(msg)
        #except Exception as e:
        #    c_log.log_error()
        n = msg
        self.queue.put(n)

    #def handler(self, signum, frame):
    #    self.stop()

    def resetTimer(self, action):
        if (action == 'reset'):
            self.time_thread.cancel()
            self.time_thread = threading.Timer(self.timer_lapse, self.on_timeout)
        self.time_thread.start()

    def prepare_timeout(self):
        self.resetTimer('reset')

    @abstractmethod
    def on_timeout(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass
