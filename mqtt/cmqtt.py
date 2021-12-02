import paho.mqtt.client as mqtt
import threading
from queue import Queue
import json
import calendar
import time
import signal
import os
import socket
import netifaces
#import client_config as config
from functools import reduce
import random
import logging

import re

logger = logging.getLogger(__name__)

class CMQTT (threading.Thread):
    def __init__(self, _queue, server, 
        mqtt_username= "jetson",
        mqtt_password= "Etag1234",
        mqtt_broker= "brokertest.etag-hk.com",
        ca_cert= "/home/pi/certs/MyRootCaCert.pem",
        client_name= "jetson_dev",
        alert_topic= "TEST/JETSON/",
        sensor_topic="TEST/JETSON/",
        output_uri=None #"mqtt://brokertest.etag-hk.com:1883"
    ):
        random.seed()
        threading.Thread.__init__(self)

        self.mqtt_broker_primary = re.sub(r"\:[0-9]+", "", re.sub(r"mqtt\:\/\/", "", output_uri)) if output_uri else None
        self.daemon = True
        self.mqtt_broker = self.mqtt_broker_primary or mqtt_broker
        self.user = mqtt_username
        self.passwd = mqtt_password

        #self.gatewayId = self.get_hw_address()
        #self.alertTopic = alert_topic+self.gatewayId
        #self.sensorTopic = sensor_topic+self.gatewayId
        self.ca_cert = ca_cert
        self.queue = _queue
        self.callback = server
        #self.gatewayId + \
        client_name = client_name + "_" + str(random.randint(0, 999999)).zfill(6)
        logger.info("client_name: " + client_name)
        self.connectionFlag = False
        self.client = mqtt.Client(client_id=client_name, clean_session=True)
        self.client.username_pw_set(self.user, self.passwd)
        # self.client.tls_set(self.ca_cert)
        # self.client.tls_insecure_set(True)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.reconnect_count = 0
        self.server = server
        self.continous_loop = True
        self.tran_counter = 0
        #self.sensorType = config.sensor_type
        #self.sensorTypeId = config.sensor_type_id
        #self.ifname = config.ifname

        self.sensorTopic = sensor_topic


    def stop(self):
        self.continous_loop = False
        logger.info("stop mqtt")

    def get_counter(self):
        self.tran_counter = self.tran_counter+1
        return self.tran_counter

    def run(self):
        ip_addr = self.get_ip_address()
        logger.info("MQTT connecting from " + ip_addr)
        try:
            #logger.info("ca_cert =" + self.ca_cert)
            logger.info("1883 without ca_cert")
            self.client.connect(self.mqtt_broker, 1883, 60)
            logger.info("Connected to MQTT broker")
        except Exception as e:
            logger.error(e)

        self.client.loop_start()
        while(self.continous_loop):
            if(self.connectionFlag):
                try:
                    item = self.queue.get()
                    #logger.debug(item)
                    message_object = json.loads(item)
                    current_time = calendar.timegm(time.gmtime())
                    message_object['current_time'] = current_time
                    #message_topic = "test"
                    l = json.dumps(message_object)
                    #print("sensorTopic", self.sensorTopic)
                    #print("sensorMessage", l)
                    self.client.publish(self.sensorTopic, l, 1)
                except Exception as e:
                    logger.error(e)
                    self.callback.stop()
                    break
            else:
                time.sleep(1)

        self.client.loop_stop()

    def get_ip_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(10)
        while(True):
            try:
                s.connect(("8.8.8.8", 80))
                s.settimeout(None)
                break
            except socket.error:
                time.sleep(2.0)
                continue
        #logger.debug(s.getsockname()[0])
        return s.getsockname()[0]

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connectionFlag = True
            self.reconnect_count = 0
            logger.info("MQTT connected ok")
        else:
            logger.error("MQTT connection refused")

    def on_disconnect(self, client, userdata, rc):
        logger.info("connection disconnect")
        if rc != 0:
            self.connectionFlag = False
            self.reconnect_count = self.reconnect_count + 1
            if(self.reconnect_count == 5):
                self.callback.stop()
            logger.info("Connection refused, auto reconnect")

    #def get_hw_address(self):
    #    ifname = self.ifname
    #    return netifaces.ifaddresses(ifname)[netifaces.AF_LINK][0]['addr']
