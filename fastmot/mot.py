from enum import Enum
import logging
import cv2
import time

from .detector import SSDDetector, YoloDetector, PublicDetector
from .feature_extractor import FeatureExtractor
from .tracker import MultiTracker
from .utils.visualization import draw_trk, draw_det, draw_bkg_flow


class DetectorType(Enum):
    SSD = 0
    YOLO = 1
    PUBLIC = 2


class Mot:
    def __init__(self, size, capture_dt, config, draw=False, verbose=False):
        self.size = size
        self.draw = draw
        self.verbose = verbose
        self.detector_type = DetectorType[config['detector_type']]
        self.detector_frame_skip = config['detector_frame_skip']

        logging.info('Loading detector model...')
        if self.detector_type == DetectorType.SSD:
            self.detector = SSDDetector(self.size, config['ssd_detector'])
        elif self.detector_type == DetectorType.YOLO:
            self.detector = YoloDetector(self.size, config['yolo_detector'])
        elif self.detector_type == DetectorType.PUBLIC:
            self.detector = PublicDetector(self.size, config['public_detector'])

        logging.info('Loading feature extractor model...')
        self.extractor = FeatureExtractor(config['feature_extractor'])
        self.tracker = MultiTracker(self.size, capture_dt, self.extractor.metric, config['multi_tracker'])
        
        # reset counters
        self.frame_count = 0
        self.detector_frame_count = 0
        self.preproc_time = 0
        self.detector_time = 0
        self.extractor_time = 0
        self.association_time = 0
        self.tracker_time = 0
    
    @property
    def visible_tracks(self):
        return [track for track in self.tracker.tracks.values() if track.confirmed and track.active]
    
    def run(self, frame):
        detections = []
        if self.frame_count == 0:
            detections = self.detector(self.frame_count, frame)
            self.tracker.initiate(frame, detections)
        else:
            if self.frame_count % self.detector_frame_skip == 0:
                tic = time.perf_counter()
                self.detector.detect_async(self.frame_count, frame)
                self.preproc_time += time.perf_counter() - tic
                tic = time.perf_counter()
                self.tracker.compute_flow(frame)
                detections = self.detector.postprocess()
                self.detector_time += time.perf_counter() - tic
                tic = time.perf_counter()
                self.extractor.extract_async(frame, detections)
                self.tracker.step_kalman_filter(self.frame_count)
                embeddings = self.extractor.postprocess()
                self.extractor_time += time.perf_counter() - tic
                tic = time.perf_counter()
                self.tracker.update(self.frame_count, detections, embeddings)
                self.association_time += time.perf_counter() - tic
                self.detector_frame_count += 1
            else:
                tic = time.perf_counter()
                self.tracker.track(self.frame_count, frame)
                self.tracker_time += time.perf_counter() - tic

        if self.draw:
            self._draw(frame, detections, self.verbose)

        self.frame_count += 1

    def initiate(self):
        self.frame_count = 0

    def _draw(self, frame, detections, verbose=False):
        for track in self.visible_tracks:
            draw_trk(frame, track, draw_flow=verbose)
        if verbose:
            for det in detections:
                draw_det(frame, det)
            draw_bkg_flow(frame, self.tracker)
        cv2.putText(frame, f'visible: {len(self.visible_tracks)}', (30, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2, cv2.LINE_AA)
