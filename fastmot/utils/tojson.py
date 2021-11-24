import json
import numpy as np

"""
{"unconfirmed": {"tlbr": [58.0, 412.0, 89.0, 488.0], "label": 1, "trk_id": 10}}
{"detected": {"tlbr": [1012.0, 365.0, 1042.0, 454.0], "label": 1, "trk_id": 11}}
{"found": {"tlbr": [1020.0, 350.0, 1046.0, 435.0], "label": 1, "trk_id": 11}}
"""

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)