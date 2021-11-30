# PoC only!

# https://github.com/miguelgrinberg/python-socketio

import socketio

# Keep logger=true otherwise it is impossible to debug
sio = socketio.Client(logger=True, engineio_logger=True)

primary_chanel = "live/fastmot"

expected_url = "wss://webtest.etag-hk.com/taihang/api/socketio/?EIO=3&transport=websocket"

#https://github.com/miguelgrinberg/python-socketio/blob/main/src/socketio/client.py
#https://github.com/miguelgrinberg/python-engineio/blob/main/src/engineio/client.py
#Why skip all the sub-directory?
io_server_url = 'ws://192.168.2.114:3465' #'/taihang/api/live/fastmot'

def get_io_server_url():
    return io_server_url

@sio.event
def message(data):
    print('I received a message!')
    print(data)

@sio.on('connect') #, namespace=primary_chanel
def connect(): #on_
    print("I'm connected to the server")

@sio.event
def connect_error(data):
    print("The connection failed!")

@sio.event
def disconnect():
    print("I'm disconnected!")

# Solved.
sio.connect(url=io_server_url, socketio_path="taihang/api/socketio", transports="websocket") #, namespaces=[primary_chanel]

# engineio.__version__ = '4.2.1dev'

print('my sid is', sio.sid)

# https://github.com/feathersjs/feathers/issues/1471
# https://github.com/miguelgrinberg/python-socketio/issues/321

test_payload = {
    'deviceId': 'fastmot',
    'foo': 'bar'
}

sio.emit("create", (primary_chanel, test_payload))
