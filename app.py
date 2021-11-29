#!/usr/bin/env python3

from pathlib import Path
from types import SimpleNamespace
import argparse
import logging
import json
import cv2
import base64
from numpyencoder import NumpyEncoder

import fastmot
import fastmot.models
from fastmot.utils import ConfigDecoder, Profiler
from fastmot.videoio import VideoIO

from logging.handlers import RotatingFileHandler

from functools import partial
from argparse import Namespace
from PIL import Image
from io import BytesIO

from mqtt import mqttClient

# set up logging
LOG_PATH = 'site/fastmot.log' 

def on_trackevt(trk_evt, mqtt_client=None):
    json_object = json.dumps(trk_evt, cls=NumpyEncoder)
    if mqtt_client is not None and callable(mqtt_client.myCallback):
        mqtt_client.myCallback(json_object)
        #print(json_object)
    else: 
        print(json_object)

#frame: np.ndarray from cv2
#https://stackoverflow.com/questions/43310681/how-to-convert-python-numpy-array-to-base64-output
def frame_to_img_b64(frame):
    pil_img = Image.fromarray(frame)
    buff = BytesIO()
    pil_img.save(buff, format="PNG")
    new_image_string = base64.b64encode(buff.getvalue()).decode("utf-8")
    #print(new_image_string)
    return new_image_string

def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    optional = parser._action_groups.pop()
    required = parser.add_argument_group('required arguments')
    group = parser.add_mutually_exclusive_group()
    required.add_argument('-i', '--input-uri', metavar="URI", required=True, help=
                          'URI to input stream\n'
                          '1) image sequence (e.g. %%06d.jpg)\n'
                          '2) video file (e.g. file.mp4)\n'
                          '3) MIPI CSI camera (e.g. csi://0)\n'
                          '4) USB camera (e.g. /dev/video0)\n'
                          '5) RTSP stream (e.g. rtsp://<user>:<password>@<ip>:<port>/<path>)\n'
                          '6) HTTP stream (e.g. http://<user>:<password>@<ip>:<port>/<path>)\n')
    optional.add_argument('-c', '--config', metavar="FILE",
                          default=Path(__file__).parent / 'cfg' / 'mot.json',
                          help='path to JSON configuration file')
    optional.add_argument('-l', '--labels', metavar="FILE",
                          help='path to label names (e.g. coco.names)')
    optional.add_argument('-o', '--output-uri', metavar="URI",
                          help='URI to output video file')
    optional.add_argument('-t', '--txt', metavar="FILE",
                          help='path to output MOT Challenge format results (e.g. MOT20-01.txt)')
    optional.add_argument('-m', '--mot', action='store_true', help='run multiple object tracker')
    optional.add_argument('-s', '--show', action='store_true', help='show visualizations')
    group.add_argument('-q', '--quiet', action='store_true', help='reduce output verbosity')
    group.add_argument('-v', '--verbose', action='store_true', help='increase output verbosity')
    parser._action_groups.append(optional)
    args = parser.parse_args()
    if args.txt is not None and not args.mot:
        raise parser.error('argument -t/--txt: not allowed without argument -m/--mot')
    
    log_file_handler = RotatingFileHandler(LOG_PATH, maxBytes=8 * 1000 * 1000, backupCount=8)
    
    logging.basicConfig(format='%(asctime)s [%(levelname)8s] %(filename)s.%(lineno)d: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', handlers=[log_file_handler]) #, filename=LOG_PATH
    
    logger = logging.getLogger(fastmot.__name__)
    if args.quiet:
        logger.setLevel(logging.WARNING)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # load config file
    with open(args.config) as cfg_file:
        config = json.load(cfg_file, cls=ConfigDecoder, object_hook=lambda d: SimpleNamespace(**d))

    # load mqtt client if enabled
    if config.mqtt_cfg is not None:
        #args_merged = Namespace(**vars(args), **vars(config.mqtt_cfg))

        mqtt_output_uri = args.output_uri if VideoIO._parse_uri(args.output_uri or "http://localhost/") == 7 else None
        mqtt_client = mqttClient(output_uri=mqtt_output_uri, **vars(config.mqtt_cfg))
        mqtt_client.start()

    # load labels if given
    if args.labels is not None:
        with open(args.labels) as label_file:
            label_map = label_file.read().splitlines()
            fastmot.models.set_label_map(label_map)

    stream = fastmot.VideoIO(config.resize_to, args.input_uri, args.output_uri, **vars(config.stream_cfg))

    mot = None
    txt = None
    if args.mot:
        draw = args.show or args.output_uri is not None
        mot = fastmot.MOT(
            config.resize_to, 
            draw=draw, on_trackevt=partial(on_trackevt, mqtt_client=mqtt_client),
            **vars(config.mot_cfg)
        )
        mot.reset(stream.cap_dt)
    if args.txt is not None:
        Path(args.txt).parent.mkdir(parents=True, exist_ok=True)
        txt = open(args.txt, 'w')
    if args.show:
        cv2.namedWindow('Video', cv2.WINDOW_AUTOSIZE)

    logger.info('Starting video capture...')
    stream.start_capture()
    try:
        with Profiler('app') as prof:
            while not args.show or cv2.getWindowProperty('Video', 0) >= 0:
                frame = stream.read()
                if frame is None:
                    break

                if args.mot:
                    mot.step(frame)
                    if txt is not None:
                        for track in mot.visible_tracks():
                            tl = track.tlbr[:2] / config.resize_to * stream.resolution
                            br = track.tlbr[2:] / config.resize_to * stream.resolution
                            w, h = br - tl + 1
                            txt.write(f'{mot.frame_count},{track.trk_id},{tl[0]:.6f},{tl[1]:.6f},'
                                      f'{w:.6f},{h:.6f},-1,-1,-1\n')

                if args.show:                   
                    cv2.imshow('Video', frame)
                    if cv2.waitKey(1) & 0xFF == 27:
                        break

                if args.output_uri is not None:
                    logger.debug("writing frame...")
                    stream.write(frame)
                    try:
                        img = frame_to_img_b64(frame)
                        on_trackevt({'frame': len(img)}, mqtt_client=mqtt_client)
                    except:
                        pass
                                      
    finally:
        # clean up resources
        if txt is not None:
            txt.close()
        stream.release()
        cv2.destroyAllWindows()

    # timing statistics
    if args.mot:
        avg_fps = round(mot.frame_count / prof.duration)
        logger.info('Average FPS: %d', avg_fps)
        mot.print_timing_info()


if __name__ == '__main__':
    main()
