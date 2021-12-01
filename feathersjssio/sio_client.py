# https://github.com/miguelgrinberg/python-socketio
import socketio

import threading
import calendar
import time
import os
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class SIOClient():

    def parseURL(self, ws_url):
        sep = '/'
        up = urlparse(ws_url)
        ps = up.path.split(sep) #['taihang', 'api', 'live', 'fastmot']
        ws_scheme = up.scheme
        if ws_scheme == 'https':
            ws_scheme = 'wss'
        elif ws_scheme == 'http':
            ws_scheme = 'ws'

        #"ws://192.168.2.114:3465/taihang/api/live/fastmot"
        #"wss://webtest.etag-hk.com/taihang/api/live/fastmot"
        #   "WS_URL": "http://localhost:3465",
        #   "WS_PATH": "/taihang/api/socketio/",
        
        #https://github.com/miguelgrinberg/python-socketio/blob/main/src/socketio/client.py
        #https://github.com/miguelgrinberg/python-engineio/blob/main/src/engineio/client.py
        #Why skip all the sub-directory?
        io_server_url = '%s://%s' % (ws_scheme, up.netloc)
        transports = None #"websocket"
        
        #print(ps)
        if len(ps) == 5:
            socketio_path = '%s/socketio' % (sep.join(ps[1:3]))
            primary_chanel = sep.join(ps[3:])
        else:
            print("Parse URL failed. Fallback to default value...")
            print("e.g. http://localhost/appname/api/live/fastmot")
            socketio_path = 'socket.io' #default
            primary_chanel = 'my message' #as in official guideline
        
        #io_server_url = 'ws://192.168.2.114:3465' #'/taihang/api/live/fastmot'
        #socketio_path = "taihang/api/socketio"
        #primary_chanel = "live/fastmot"
        return io_server_url, socketio_path, transports, primary_chanel

    def __init__(self,   
        output_uri = None,
        FEATHERSJS_SOCKET = {}
    ):
        # If it needs inheritance
        # super().__init__(timer_lapse)
        
        self.output_uri = output_uri
        io_server_url, socketio_path, transports, primary_chanel = self.parseURL(self.output_uri)
        self.io_server_url = io_server_url
        self.socketio_path = socketio_path
        self.transports = transports
        self.primary_chanel = primary_chanel

        # Keep logger=true otherwise it is impossible to debug
        # #logger=FEATHERSJS_SOCKET['sio_logger'], engineio_logger=FEATHERSJS_SOCKET['engineio_logger']
        self.sio = socketio.Client(**vars(FEATHERSJS_SOCKET)) #logger=True, engineio_logger=True

        logger.info("FeathersJS socket.io Connection initialize")

        @self.sio.event
        def message(data):
            print('I received a message!')
            print(data)

        @self.sio.on('connect') #, namespace=primary_chanel
        def connect(): #on_
            print("I'm connected to the server")

        @self.sio.event
        def connect_error(data):
            print("The connection failed!")

        @self.sio.event
        def disconnect():
            print("I'm disconnected!")

    def start(self):
        #self.mqtt.start()
        #self.create_waterlevel_connection()
        
        # Solved.
        self.sio.connect(url=self.io_server_url, socketio_path=self.socketio_path, transports=self.transports)

        # engineio.__version__ = '4.2.1dev'

        #print('my sid is', self.sio.sid)
        self.resetTimer('start')

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

        print('put_msg: ', self.primary_chanel)
        self.sio.emit("create", (self.primary_chanel, sensor_data))
    
    def on_trackevt(self, sensor_data):
        print('on_trackevt()')
        #logger.info('raw message: ' + str(sensor_data))
        self.put_msg(sensor_data)