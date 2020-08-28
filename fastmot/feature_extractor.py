from multiprocessing.pool import ThreadPool
import numpy as np
import numba as nb
import cv2

from .utils import InferenceBackend
from .utils.rect import multi_crop
from .models import *


class FeatureExtractor:
    def __init__(self):
        self.model = OSNet025
        self.batch_size = 32
        self.input_size = np.prod(self.model.INPUT_SHAPE)
        self.feature_dim = self.model.OUTPUT_LAYOUT
        self.backend = InferenceBackend(self.model, self.batch_size)
        self.pool = ThreadPool()

        self.embeddings = []
        self.num_features = 0

    def __call__(self, frame, detections):
        self.extract_async(frame, detections)
        return self.postprocess()

    @property
    def metric(self):
        return self.model.METRIC

    def extract_async(self, frame, detections):
        imgs = multi_crop(frame, detections.tlbr)
        self.embeddings, cur_imgs = [], []
        for offset in range(0, len(imgs), self.batch_size):
            cur_imgs = imgs[offset:offset + self.batch_size]
            self.pool.starmap(self._preprocess, enumerate(cur_imgs))
            if offset > 0:
                embedding_out = self.backend.synchronize()[0]
                self.embeddings.append(embedding_out)
            self.backend.infer_async()
        self.num_features = len(cur_imgs)

    def postprocess(self):
        if self.num_features == 0:
            return np.empty((0, self.feature_dim))

        embedding_out = self.backend.synchronize()[0][:self.num_features * self.feature_dim]
        self.embeddings.append(embedding_out)
        embeddings = np.concatenate(self.embeddings).reshape(-1, self.feature_dim)
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings

    def _preprocess(self, idx, img):
        img = cv2.resize(img, self.model.INPUT_SHAPE[:0:-1])
        self._normalize(img, idx, self.backend.input.host, self.input_size)

    @staticmethod
    @nb.njit(fastmath=True, nogil=True, cache=True)
    def _normalize(img, idx, out, size):
        offset = idx * size
        # BGR to RGB
        img = img[..., ::-1]
        # HWC -> CHW
        img = img.transpose(2, 0, 1)
        # Normalize using ImageNet's mean and std
        img = img * (1 / 255)
        img[0, ...] = (img[0, ...] - 0.485) / 0.229
        img[1, ...] = (img[1, ...] - 0.456) / 0.224
        img[2, ...] = (img[2, ...] - 0.406) / 0.225
        out[offset:offset + size] = img.ravel()
