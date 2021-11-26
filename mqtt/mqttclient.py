import threading
from .abstract_server import abstractServer
from .cmqtt import CMQTT
import calendar
import time
import os
import logging

logger = logging.getLogger(__name__)

class mqttClient(abstractServer):

    def __init__(self,   
        timer_lapse=200,
        MQTT_SOCKET={}
    ):
        super().__init__(timer_lapse)
        self.mqtt = CMQTT(self.queue, self, **vars(MQTT_SOCKET))
        self.lock = threading.Lock()
        self.contin = True
        self.deviceconnection = None
        logger.info("MQTT Connection initialize")

    def start(self):
        self.mqtt.start()
        #self.create_waterlevel_connection()
        self.resetTimer('start')

    def stop(self):
        super().stop()
        self.contin = False
        self.mqtt.stop()
        # self.deviceconnection.stop()
        logger.info("stop program in 5 seconds...")
        time.sleep(5)
        os._exit(0)
        #logger.info("restarting...")
        #self.start()

    def on_timeout(self):
        self.prepare_timeout()

    def create_waterlevel_connection(self):
        try:
            # Start thread with callback
            #self.deviceconnection = NCDEnterprise(client_config.NCD_SERIALPORT.SERIAL_PORT, client_config.NCD_SERIALPORT.BAUD_RATE, self.myCallback)
            #self.deviceconnection = MiniModbusCallback("TCP", self.myCallback)

            #Currently device connection is done in somewhere else
            self.deviceconnection = None
        except Exception as e:
            logger.error(e)
            self.stop()

    def myCallback(self, sensor_data):
        logger.info('raw message: ' + str(sensor_data))
        # for prop in sensor_data:
        #    logger.debug(prop + ' ' + str(sensor_data[prop]))
        # self.battery_alert(sensor_data['nodeId'], sensor_data['battery'])
        # try:
        #current_time = calendar.timegm(time.gmtime())
        #for d in sensor_data:
        #    d['update_time'] = current_time
        self.put_msg(sensor_data)
        # for sd in sensor_data:
        #    self.put_msg(sd)
        # except Exception as e:
        #    logger.error(e)
        #    self.stop()