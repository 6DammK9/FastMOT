from collections import OrderedDict
import numpy as np
import numba as nb
import logging
import time
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from cython_bbox import bbox_overlaps

from .track import Track
from .flow import Flow
from .kalman_filter import MeasType, KalmanFilter
from .utils.rect import as_rect, to_tlbr, intersection, warp


CHI_SQ_INV_95 = 9.4877 # 0.95 quantile of the chi-square distribution (4 DOF)
INF_COST = 1e5


class MultiTracker:
    def __init__(self, size, dt, metric, config):
        self.size = size
        self.metric = metric
        self.max_age = config['max_age']
        self.age_factor = config['age_factor']
        self.motion_weight = config['motion_weight']
        self.max_feature_cost = config['max_feature_cost']
        self.min_iou_cost = config['min_iou_cost']
        self.max_reid_cost = config['max_reid_cost']
        self.duplicate_iou = config['duplicate_iou']
        self.min_register_conf = config['min_register_conf']
        self.lost_buf_size = config['lost_buf_size']
        self.n_init = config['n_init']
        
        self.next_id = 1
        self.tracks = {}
        self.lost = OrderedDict()
        self.kf = KalmanFilter(dt, self.n_init, config['kalman_filter'])
        self.flow = Flow(self.size, config['optical_flow'])
        self.frame_rect = to_tlbr((0, 0, *self.size))

        self.flow_bboxes = {}
        self.H_camera = None

    def compute_flow(self, frame):
        self.flow_bboxes, self.H_camera = self.flow.predict(frame, self.tracks)
        if self.H_camera is None:
            # clear tracks when camera motion estimation failed
            self.tracks.clear()

    def step_kalman_filter(self, frame_id):
        for trk_id, track in list(self.tracks.items()):
            flow_bbox = self.flow_bboxes.get(trk_id)
            time_since_acquired = frame_id - track.start_frame
            if time_since_acquired <= self.n_init:
                if flow_bbox is not None:
                    if time_since_acquired == self.n_init:
                        # initialize kalman filter
                        track.state = self.kf.initiate(track.init_tlbr, flow_bbox)
                    else:
                        track.init_tlbr = warp(track.init_tlbr, self.H_camera) 
                        track.tlbr = flow_bbox
                else:
                    logging.warning('Init failed: %s', track)
                    del self.tracks[trk_id]
            else:
                mean, cov = track.state
                # track using kalman filter and flow measurement
                mean, cov = self.kf.warp(mean, cov, self.H_camera)
                mean, cov = self.kf.predict(mean, cov)
                if flow_bbox is not None and track.active:
                    # give large flow uncertainty for occluded objects
                    std_multiplier = max(self.age_factor * track.age, 1)
                    mean, cov = self.kf.update(mean, cov, flow_bbox, MeasType.FLOW, std_multiplier)
                next_tlbr = as_rect(mean[:4])
                track.state = (mean, cov)
                track.tlbr = next_tlbr
                if intersection(next_tlbr, self.frame_rect) is None:
                    logging.info('Out: %s', track)
                    if track.confirmed:
                        self._mark_lost(trk_id)
                    else:
                        del self.tracks[trk_id]

    def track(self, frame_id, frame):
        tic = time.perf_counter()
        self.compute_flow(frame)
        logging.debug('flow %f', time.perf_counter() - tic)
        tic = time.perf_counter()
        self.step_kalman_filter(frame_id)
        logging.debug('kalman filter %f', time.perf_counter() - tic)

    def initiate(self, frame, detections):
        """
        Initialize the tracker from detections in the first frame
        """
        if self.tracks:
            self.tracks.clear()
        self.flow.initiate(frame)
        for det in detections:
            new_track = Track(det.tlbr, det.label, self.next_id, 0)
            self.tracks[self.next_id] = new_track
            logging.debug('Detected: %s', new_track)
            self.next_id += 1

    def update(self, frame_id, detections, embeddings):
        """
        Update tracks using detections
        """
        det_ids = list(range(len(detections)))
        confirmed = [trk_id for trk_id, track in self.tracks.items() if track.confirmed]
        unconfirmed = [trk_id for trk_id, track in self.tracks.items() if not track.confirmed]

        # association with motion and embeddings
        cost = self._matching_cost(confirmed, detections, embeddings)
        matches1, u_trk_ids1, u_det_ids = self._linear_assignment(cost, confirmed, det_ids)

        # 2nd association with iou
        candidates = unconfirmed + [trk_id for trk_id in u_trk_ids1 if self.tracks[trk_id].active]
        u_trk_ids1 = [trk_id for trk_id in u_trk_ids1 if not self.tracks[trk_id].active]
        u_detections = detections[u_det_ids]
        cost = self._iou_cost(candidates, u_detections)
        matches2, u_trk_ids2, u_det_ids = self._linear_assignment(cost, candidates, u_det_ids, maximize=True)

        matches = matches1 + matches2
        u_trk_ids = u_trk_ids1 + u_trk_ids2

        # Re-id with lost tracks
        lost_ids = list(self.lost.keys())
        u_detections, u_embeddings = detections[u_det_ids], embeddings[u_det_ids]
        cost = self._reid_cost(u_detections, u_embeddings)
        reid_matches, _, u_det_ids = self._linear_assignment(cost, lost_ids, u_det_ids)

        updated, aged = [], []

        # update matched tracks
        for trk_id, det_id in matches:
            track = self.tracks[trk_id]
            det = detections[det_id]
            mean, cov = self.kf.update(*track.state, det.tlbr, MeasType.DETECTOR)
            next_tlbr = as_rect(mean[:4])
            track.state = (mean, cov)
            track.tlbr = next_tlbr
            track.update_features(embeddings[det_id])
            track.age = 0
            if not track.confirmed:
                track.confirmed = True
                logging.info('Found: %s', track)
            if intersection(next_tlbr, self.frame_rect) is not None:
                updated.append(trk_id)
            else:
                logging.info('Out: %s', track)
                self._mark_lost(trk_id)

        for (trk_id, det_id) in reid_matches:
            track = self.lost[trk_id]
            det = detections[det_id]
            track.reactivate(frame_id, det.tlbr, embeddings[det_id])
            self.tracks[trk_id] = track
            logging.info('Re-identified: %s', track)
            updated.append(trk_id)
            del self.lost[trk_id]

        # clean up lost tracks
        for trk_id in u_trk_ids:
            track = self.tracks[trk_id]
            if not track.confirmed:
                logging.debug('Unconfirmed: %s', track)
                del self.tracks[trk_id]
                continue
            track.age += 1
            if track.age > self.max_age:
                logging.info('Lost: %s', track)
                self._mark_lost(trk_id)
            else:
                aged.append(trk_id)

        # register new detections
        for det_id in u_det_ids:
            det = detections[det_id]
            if det.conf > self.min_register_conf:
                new_track = Track(det.tlbr, det.label, self.next_id, frame_id)
                self.tracks[self.next_id] = new_track
                logging.debug('Detected: %s', new_track)
                updated.append(self.next_id)
                self.next_id += 1

        self._remove_duplicate(updated, aged)

    def _mark_lost(self, trk_id):
        self.lost[trk_id] = self.tracks[trk_id]
        if len(self.lost) > self.lost_buf_size:
            self.lost.popitem(last=False)
        del self.tracks[trk_id]

    def _matching_cost(self, trk_ids, detections, embeddings):
        if len(trk_ids) == 0 or len(detections) == 0:
            return np.empty((len(trk_ids), len(detections)))

        features = [self.tracks[trk_id].smooth_feature for trk_id in trk_ids]
        cost = cdist(features, embeddings, self.metric)
        for i, trk_id in enumerate(trk_ids):
            track = self.tracks[trk_id]
            motion_dist = self.kf.motion_distance(*track.state, detections.tlbr)
            cost[i] = self._fuse_motion(cost[i], motion_dist, self.max_feature_cost, 
                track.label, detections.label, self.motion_weight)
        return cost

    def _iou_cost(self, trk_ids, detections):
        if len(trk_ids) == 0 or len(detections) == 0:
            return np.empty((len(trk_ids), len(detections)))

        # make sure associated pair has the same class label
        trk_labels = np.array([self.tracks[trk_id].label for trk_id in trk_ids])
        trk_bboxes = np.array([self.tracks[trk_id].tlbr for trk_id in trk_ids])
        det_bboxes = detections.tlbr
        ious = bbox_overlaps(trk_bboxes, det_bboxes)
        ious = self._gate_cost(ious, self.min_iou_cost, trk_labels, detections.label, True)
        return ious
    
    def _reid_cost(self, detections, embeddings):
        if len(self.lost) == 0 or len(detections) == 0:
            return np.empty((len(self.lost), len(detections)))
            
        features = [track.smooth_feature for track in self.lost.values()]
        trk_labels = np.array([track.label for track in self.lost.values()])
        cost = cdist(features, embeddings, self.metric)
        cost = self._gate_cost(cost, self.max_reid_cost, trk_labels, detections.label, False)
        return cost

    def _linear_assignment(self, cost, trk_ids, det_ids, maximize=False):
        rows, cols = linear_sum_assignment(cost, maximize)
        unmatched_rows = list(set(range(cost.shape[0])) - set(rows))
        unmatched_cols = list(set(range(cost.shape[1])) - set(cols))
        unmatched_trk_ids = [trk_ids[row] for row in unmatched_rows]
        unmatched_det_ids = [det_ids[col] for col in unmatched_cols]
        matches = []
        if not maximize:
            for row, col in zip(rows, cols):
                if cost[row, col] < INF_COST:
                    matches.append((trk_ids[row], det_ids[col]))
                else:
                    unmatched_trk_ids.append(trk_ids[row])
                    unmatched_det_ids.append(det_ids[col])
        else:
            for row, col in zip(rows, cols):
                if cost[row, col] > 0:
                    matches.append((trk_ids[row], det_ids[col]))
                else:
                    unmatched_trk_ids.append(trk_ids[row])
                    unmatched_det_ids.append(det_ids[col])
        return matches, unmatched_trk_ids, unmatched_det_ids

    def _remove_duplicate(self, updated, aged):
        if len(updated) == 0 or len(aged) == 0:
            return

        updated_bboxes = np.array([self.tracks[trk_id].tlbr for trk_id in updated])
        aged_bboxes = np.array([self.tracks[trk_id].tlbr for trk_id in aged])

        ious = bbox_overlaps(updated_bboxes, aged_bboxes)
        idx = np.where(ious >= self.duplicate_iou)
        dup_ids = set()
        for row, col in zip(*idx):
            updated_id, aged_id = updated[row], aged[col]
            if self.tracks[updated_id].start_frame <= self.tracks[aged_id].start_frame:
                dup_ids.add(aged_id)
            else:
                dup_ids.add(updated_id)
        for trk_id in dup_ids:
            logging.debug('Duplicate ID %d removed', trk_id)
            del self.tracks[trk_id]

    @staticmethod
    @nb.njit(fastmath=True, cache=True)
    def _fuse_motion(cost, motion_dist, max_cost, label, det_labels, weight):
        gate = (cost > max_cost) | (motion_dist > CHI_SQ_INV_95) | (label != det_labels)
        cost = (1 - weight) * cost + weight * motion_dist
        cost[gate] = INF_COST
        return cost

    @staticmethod
    @nb.njit(parallel=True, fastmath=True, cache=True)
    def _gate_cost(cost, thresh, trk_labels, det_labels, maximize):
        for i in nb.prange(len(cost)):
            if maximize:
                gate = (cost[i] < thresh) | (trk_labels[i] != det_labels)
                cost[i][gate] = 0
            else:
                gate = (cost[i] > thresh) | (trk_labels[i] != det_labels)
                cost[i][gate] = INF_COST
        return cost
