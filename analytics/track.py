from pathlib import Path
import json
import numpy as np
import cv2

from .models import COCO_LABELS
from .utils import ConfigDecoder

class Track:
    with open(Path(__file__).parent / 'configs' / 'mot.json') as config_file:
        config = json.load(config_file, cls=ConfigDecoder)['Track']

    def __init__(self, label, bbox, track_id):
        self.label = label
        self.bbox = bbox
        self.init_bbox = bbox
        self.track_id = track_id

        self.age = 0
        self.frames_since_acquired = 0
        self.features = []
        self.budget = Track.config['budget']
        self.feature_pts = None
        self.prev_feature_pts = None

    def __repr__(self):
        return "Track(label=%r, bbox=%r, track_id=%r)" % (self.label, self.bbox, self.track_id)

    def __str__(self):
        return "%s ID%d at %s" % (COCO_LABELS[self.label], self.track_id, self.bbox.tlwh())

    def add_embedding(self, embedding):
        self.features.append(embedding)
        self.features = self.features[-self.budget:]

    def draw(self, frame, follow=False, draw_feature_match=False):
        bbox_color = (127, 255, 0) if follow else (0, 165, 255)
        text_color = (143, 48, 0)
        # text = "%s%d" % (COCO_LABELS[self.label], self.track_id) 
        text = str(self.track_id)
        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 1)
        cv2.rectangle(frame, self.bbox.tl(), self.bbox.br(), bbox_color, 2)
        cv2.rectangle(frame, self.bbox.tl(), (self.bbox.xmin + text_width - 1,
                        self.bbox.ymin - text_height + 1), bbox_color, cv2.FILLED)
        cv2.putText(frame, text, self.bbox.tl(), cv2.FONT_HERSHEY_SIMPLEX, 1, text_color, 2, cv2.LINE_AA)
        if draw_feature_match:
            if self.feature_pts is not None:
                [cv2.circle(frame, tuple(pt), 1, (0, 255, 255), -1) for pt in np.int_(np.round(self.feature_pts))]
                if self.prev_feature_pts is not None:
                    [cv2.line(frame, tuple(pt1), tuple(pt2), (0, 255, 255), 1, cv2.LINE_AA) for pt1, pt2 in 
                    zip(np.int_(np.round(self.prev_feature_pts)), np.int_(np.round(self.feature_pts)))]