from enum import Enum
from pathlib import Path
import json
import numpy as np
import cv2
import time

from .utils import *
from .models import *


class Detection:
    def __init__(self, bbox, label, conf, tile_id):
        self.bbox = bbox
        self.label = label
        self.conf = conf
        self.tile_id = tile_id

    def __repr__(self):
        return "Detection(bbox=%r, label=%r, conf=%r, tile_id=%r)" % (self.bbox, self.label, self.conf, self.tile_id)

    def __str__(self):
        return "%.2f %s at %s" % (self.conf, COCO_LABELS[self.label], self.bbox.cv_rect())
    
    def draw(self, frame):
        text = "%s: %.2f" % (COCO_LABELS[self.label], self.conf) 
        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 1)
        cv2.rectangle(frame, self.bbox.tl(), self.bbox.br(), (112, 25, 25), 2)
        cv2.rectangle(frame, self.bbox.tl(), (self.bbox.xmin + text_width - 1, self.bbox.ymin - text_height + 1), 
                    (112, 25, 25), cv2.FILLED)
        cv2.putText(frame, text, self.bbox.tl(), cv2.FONT_HERSHEY_SIMPLEX, 1, (102, 255, 255), 2, cv2.LINE_AA)


class ObjectDetector:
    class Type(Enum):
        TRACKING = 0
        ACQUISITION = 1

    with open(Path(__file__).parent / 'configs' / 'mot.json') as config_file:
        config = json.load(config_file, cls=ConfigDecoder)['ObjectDetector']

    def __init__(self, size, classes, detector_type):
        # initialize parameters
        self.size = size
        self.classes = set(classes)
        self.detector_type = detector_type
        self.max_det = ObjectDetector.config['max_det']
        self.batch_size = ObjectDetector.config['batch_size']
        self.tile_overlap = ObjectDetector.config['tile_overlap']
        self.merge_iou_thresh = ObjectDetector.config['merge_iou_thresh']

        self.tiles = None
        self.cur_tile = None
        if self.detector_type == ObjectDetector.Type.ACQUISITION:
            self.conf_threshold = ObjectDetector.config['acquisition']['conf_threshold']
            self.tiling_grid = ObjectDetector.config['acquisition']['tiling_grid']
            self.schedule_tiles = ObjectDetector.config['acquisition']['schedule_tiles']
            self.age_to_object_ratio = ObjectDetector.config['acquisition']['age_to_object_ratio']
            self.model = SSDInceptionV2 #SSDMobileNetV1
            self.tile_size = self.model.INPUT_SHAPE[:0:-1]
            self.tiles = self._generate_tiles()
            self.tile_ages = np.zeros(len(self.tiles))
            self.cur_tile_id = -1
        elif self.detector_type == ObjectDetector.Type.TRACKING:
            self.conf_threshold = ObjectDetector.config['tracking']['conf_threshold']
            self.model = SSDInceptionV2
            self.tile_size = self.model.INPUT_SHAPE[:0:-1]
        else:
            raise ValueError(f'Invalid detector type; must be either {ObjectDetector.Type.ACQUISITION} or
                             {ObjectDetector.Type.TRACKING}')
        assert self.max_det <= self.model.TOPK
        self.backend = InferenceBackend(self.model, self.batch_size)
        self.input_batch = np.zeros((self.batch_size, np.prod(self.model.INPUT_SHAPE)))
    
    def preprocess(self, frame, tracks={}, track_id=None):
        if self.batch_size > 1:
            for i, tile in enumerate(self.tiles):
                frame_tile = tile.crop(frame)
                frame_tile = cv2.cvtColor(frame_tile, cv2.COLOR_BGR2RGB)
                frame_tile = np.transpose(frame_tile, (2, 0, 1)) # HWC -> CHW
                self.input_batch[i] = frame_tile.ravel()
            self.input_batch = self.input_batch * (2 / 255) - 1
        else:
            if self.detector_type == ObjectDetector.Type.ACQUISITION:
                # tile scheduling
                if self.schedule_tiles:
                    sx = sy = 1 - self.tile_overlap
                    tile_num_tracks = np.zeros(len(self.tiles))
                    for tile_id, tile in enumerate(self.tiles):
                        scaled_tile = tile.scale(sx, sy)
                        for track in tracks.values():
                            if track.bbox.center() in scaled_tile or tile.contains_rect(track.bbox):
                                tile_num_tracks[tile_id] += 1
                    tile_scores = self.tile_ages * self.age_to_object_ratio + tile_num_tracks
                    self.cur_tile_id = np.argmax(tile_scores)
                    self.tile_ages += 1
                    self.tile_ages[self.cur_tile_id] = 0
                else:
                    self.cur_tile_id = (self.cur_tile_id + 1) % len(self.tiles)
                self.cur_tile = self.tiles[self.cur_tile_id]
            elif self.detector_type == ObjectDetector.Type.TRACKING:
                assert track_id in tracks
                xmin, ymin = np.int_(np.round(tracks[track_id].bbox.center() - (np.array(self.tile_size) - 1) / 2))
                xmin = max(min(self.size[0] - self.tile_size[0], xmin), 0)
                ymin = max(min(self.size[1] - self.tile_size[1], ymin), 0)
                self.cur_tile = Rect(cv_rect=(xmin, ymin, self.tile_size[0], self.tile_size[1]))

            roi = self.cur_tile.crop(roi)
            roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
            roi = np.transpose(roi, (2, 0, 1)) # HWC -> CHW
            roi = roi * (2 / 255) - 1 # Normalize to [-1.0, 1.0] interval (expected by model)
            self.input_batch[0] = roi.ravel()
        return self.input_batch

    def postprocess(self):
        det_out = self.backend.synchronize()[0]
        # print(time.perf_counter() - self.tic)
        detections = []
        for tile_idx in range(self.batch_size):
            tile = self.tiles[tile_idx] if self.batch_size > 1 else self.cur_tile
            tile_offset = tile_idx * self.model.TOPK
            for det_idx in range(self.max_det):
                offset = (tile_offset + det_idx) * self.model.OUTPUT_LAYOUT
                # index = int(det_out[offset])
                label = int(det_out[offset + 1])
                conf = det_out[offset + 2]
                if conf > self.conf_threshold and label in self.classes:
                    xmin = int(round(det_out[offset + 3] * tile.size[0])) + tile.xmin
                    ymin = int(round(det_out[offset + 4] * tile.size[1])) + tile.ymin
                    xmax = int(round(det_out[offset + 5] * tile.size[0])) + tile.xmin
                    ymax = int(round(det_out[offset + 6] * tile.size[1])) + tile.ymin
                    bbox = Rect(tf_rect=(xmin, ymin, xmax, ymax))
                    detections.append(Detection(bbox, label, conf, set([tile_idx])))
                    # print('[Detector] Detected: %s' % det)

        # merge detections across different tiles
        merged_detections = []
        merged_det_indices = set()
        for i, det1 in enumerate(detections):
            if i not in merged_det_indices:
                merged_det = Detection(det1.bbox, det1.label, det1.conf, det1.tile_id)
                for j, det2 in enumerate(detections):
                    if j not in merged_det_indices:
                        if not det2.tile_id.issubset(merged_det.tile_id) and merged_det.label == det2.label:
                            if merged_det.bbox.contains_rect(det2.bbox) or iou(merged_det.bbox, det2.bbox) > self.merge_iou_thresh:
                                merged_det.bbox |= det2.bbox
                                merged_det.conf = max(merged_det.conf, det2.conf) 
                                merged_det.tile_id |= det2.tile_id
                                merged_det_indices.add(i)
                                merged_det_indices.add(j)
                if i in merged_det_indices:
                    merged_detections.append(merged_det)
        detections = np.delete(detections, list(merged_det_indices))
        detections = np.append(detections, merged_detections)
        return detections

    def detect(self, frame, tracks={}, track_id=None):
        self.detect_async(frame, tracks, track_id)
        return self.postprocess()

    def detect_async(self, frame, tracks={}, track_id=None):
        inp = self.preprocess(frame, tracks, track_id)
        self.backend.infer_async(inp)

    def get_tiling_region(self):
        assert self.detector_type == ObjectDetector.Type.ACQUISITION and len(self.tiles) > 0
        return Rect(tf_rect=(self.tiles[0].xmin, self.tiles[0].ymin, self.tiles[-1].xmax, self.tiles[-1].ymax))

    def draw_tile(self, frame):
        if self.cur_tile is not None:
            cv2.rectangle(frame, self.cur_tile.tl(), self.cur_tile.br(), 0, 2)
        else:
            [cv2.rectangle(frame, tile.tl(), tile.br(), 0, 2) for tile in self.tiles]

    def _generate_tiles(self):
        width, height = self.size
        tile_width, tile_height = self.tile_size
        step_width = (1 - self.tile_overlap) * tile_width
        step_height = (1 - self.tile_overlap) * tile_height
        total_width = (self.tiling_grid[0] - 1) * step_width + tile_width
        total_height = (self.tiling_grid[1] - 1) * step_height + tile_height
        assert total_width <= width and total_height <= height, "Frame size not large enough for %dx%d tiles" % self.tiling_grid
        x_offset = width // 2 - total_width // 2
        y_offset = height // 2 - total_height // 2
        tiles = [Rect(cv_rect=(int(c * step_width + x_offset), int(r * step_height + y_offset), tile_width, tile_height)) for r in
                range(self.tiling_grid[1]) for c in range(self.tiling_grid[0])]
        return tiles
