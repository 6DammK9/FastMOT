# https://github.com/miguelgrinberg/python-socketio
import socketio

import random
import threading
import calendar
import time
import os
import logging
from urllib.parse import urlparse
from fastmot.utils import NpEncoder
import json

logger = logging.getLogger(__name__)

class SIOClient(threading.Thread):

    def __init__(self,   
        output_uri = None,
        device_id = "unknown",
        FEATHERSJS_SOCKET = {}
    ):
        # Create as a new thread
        random.seed()
        threading.Thread.__init__(self)
        
        self.output_uri = output_uri
        io_server_url, socketio_path, transports, primary_chanel = self.parseURL(self.output_uri)
        self.io_server_url = io_server_url
        self.socketio_path = socketio_path
        self.transports = transports
        self.primary_chanel = primary_chanel
        self.device_id = device_id

        #self.cond = threading.Condition()

        # Keep logger=true otherwise it is impossible to debug
        # #logger=FEATHERSJS_SOCKET['sio_logger'], engineio_logger=FEATHERSJS_SOCKET['engineio_logger']
        self.sio = socketio.Client(**vars(FEATHERSJS_SOCKET)) #logger=True, engineio_logger=True

        logger.info("FeathersJS socket.io Connection initialize")

        @self.sio.event
        def message(data):
            logger.info('on_message: ', data)

        @self.sio.on('connect') #, namespace=primary_chanel
        def connect(): #on_
            logger.info('on_connect')

        @self.sio.event
        def connect_error(data):
            logger.info('on_connection_error')

        @self.sio.event
        def disconnect():
            logger.info('on_disconnect')

    #Inherted from threading.Thread
    #def start(self):
    #    print("Thread start")
    #    logger.info("start")
    #    pass

    def run(self):
        #print("Thread run")
        logger.info("run")
        
        #https://gitmemory.cn/repo/miguelgrinberg/python-socketio/issues/821
        #https://stackoverflow.com/questions/31851514/how-does-thread-init-self-in-a-class-work
        #Note: Upon timeout, this client suddenly BLOCK IO!
        #print("url", self.io_server_url)
        self.sio.connect(url=self.io_server_url, socketio_path=self.socketio_path, 
            transports=self.transports, wait_timeout=30
        )

        # engineio.__version__ = '4.2.1dev'

        #print('my sid is', self.sio.sid)
        logger.info("Connected as SID: ", self.sio.sid)
        #self.resetTimer('start')

        #Send message immediately?
        if False:
            test_payload = {
                'deviceId': 'fastmot',
                'foo': 'bar'
            }
            print("Sending test payload...")
            self.sio.emit("create", (self.primary_chanel, test_payload))

    def stop(self):
        self.sio.disconnect()
        # self.deviceconnection.stop()
        #logger.info("stop program in 5 seconds...")
        #time.sleep(5)
        #os._exit(0)
        #logger.info("restarting...")
        #self.start()

    def put_msg(self, sensor_data):
        # https://github.com/feathersjs/feathers/issues/1471
        # https://github.com/miguelgrinberg/python-socketio/issues/321

        #sensor_data = {
        #    'deviceId': 'fastmot',
        #    'foo': 'bar'
        #}

        #print('put_msg: ', self.primary_chanel)
        #print(sensor_data)
        #sensor_data = json.dumps(sensor_data, cls=NpEncoder) #NumpyEncoder
        #https://socket.io/docs/v4/namespaces/
        payload = {
            'deviceId': self.device_id, 
            'sensor_data': sensor_data
        }
        self.sio.emit("create", (self.primary_chanel, payload))
    
    def on_trackevt(self, sensor_data):
        #logger.info('on_trackevt()')
        #logger.info('raw message: ' + str(sensor_data))
        self.put_msg(sensor_data)

    def parseURL(self, ws_url):
        sep = '/'
        up = urlparse(ws_url)
        ps = up.path.split(sep) #['taihang', 'api', 'live', 'fastmot']
        ws_scheme = up.scheme
        #print("old ws_scheme", ws_scheme)
        if ws_scheme == 'https':
            ws_scheme = 'wss'
        elif ws_scheme == 'http':
            ws_scheme = 'ws'
        #print("new ws_scheme", ws_scheme)

        #"ws://192.168.2.114:3465/taihang/api/live/fastmot"
        #"wss://webtest.etag-hk.com/taihang/api/live/fastmot"
        #   "WS_URL": "http://localhost:3465",
        #   "WS_PATH": "/taihang/api/socketio/",
        
        #https://github.com/miguelgrinberg/python-socketio/blob/main/src/socketio/client.py
        #https://github.com/miguelgrinberg/python-engineio/blob/main/src/engineio/client.py
        #Why skip all the sub-directory?
        io_server_url = '%s://%s' % (ws_scheme, up.netloc)
        transports = "websocket" #polling
        
        #print(ps)
        if len(ps) == 5:
            socketio_path = '%s/socketio' % (sep.join(ps[1:3]))
            primary_chanel = sep.join(ps[3:])
        else:
            print("Parse URL failed. Fallback to default value...")
            print("e.g. http://localhost/appname/api/live/fastmot")
            socketio_path = 'socket.io' #default
            primary_chanel = 'my message' #as in official guideline
        
        #https://stackoverflow.com/questions/66441954/socketio-packet-queue-is-empty-aborting-error-when-sending-message-from-serve
        
        #io_server_url = 'ws://192.168.2.114:3465' #'/taihang/api/live/fastmot'
        #socketio_path = "taihang/api/socketio"
        #primary_chanel = "live/fastmot"
        return io_server_url, socketio_path, transports, primary_chanel