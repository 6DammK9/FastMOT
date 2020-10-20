import colorsys
import numpy as np
import cv2


GOLDEN_RATIO = 0.618033988749895


def draw_track(frame, trk, draw_flow=False):
    _draw_bbox(frame, trk.tlbr, str(trk.trk_id), _get_color(trk.trk_id), 0)
    if draw_flow:
        _draw_feature_match(frame, trk.keypoints, trk.prev_keypoints, (0, 255, 255))


def draw_detection(frame, det):
    _draw_bbox(frame, det.tlbr, f'{det.conf:.2f}', (250, 190, 212), 0)


def draw_tile(frame, detector):
    assert hasattr(detector, 'tiles')
    for tile in detector.tiles:
        tl = np.rint(tile[:2] * detector.scale_factor).astype(int)
        br = np.rint(tile[2:] * detector.scale_factor).astype(int)
        cv2.rectangle(frame, tuple(tl), tuple(br), 0, 1)


def draw_bg_flow(frame, tracker):
    _draw_feature_match(frame, tracker.flow.bg_keypoints, tracker.flow.prev_bg_keypoints, (0, 0, 255))


def _get_color(idx, s=0.8, vmin=0.7):
    idx *= 3
    h = np.fmod(idx * GOLDEN_RATIO, 1.)
    v = np.sqrt(1. - np.fmod(idx * GOLDEN_RATIO, 1 - vmin))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(255 * b), int(255 * g), int(255 * r)


def _draw_bbox(frame, tlbr, text, bbox_color, text_color):
    tlbr = tlbr.astype(int)
    tl, br = tuple(tlbr[:2]), tuple(tlbr[2:])
    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 0.7, 1)
    cv2.rectangle(frame, tl, br, bbox_color, 2)
    cv2.rectangle(frame, tl, (tl[0] + text_width - 1, tl[1] - text_height + 1), bbox_color, cv2.FILLED)
    cv2.putText(frame, text, tl, cv2.FONT_HERSHEY_DUPLEX, 0.7, text_color, 1, cv2.LINE_AA)


def _draw_feature_match(frame, cur_pts, prev_pts, color):
    if len(cur_pts) > 0:
        cur_pts = np.rint(cur_pts).astype(int)
        [cv2.circle(frame, tuple(pt), 1, color, -1) for pt in cur_pts]
        if len(prev_pts) > 0:
            prev_pts = np.rint(prev_pts).astype(int)
            [cv2.line(frame, tuple(pt1), tuple(pt2), color, 1, cv2.LINE_AA) for pt1, pt2 in
                zip(prev_pts, cur_pts)]
