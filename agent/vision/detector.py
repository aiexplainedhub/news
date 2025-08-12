from ultralytics import YOLO
from .schema import Detection

class Detector:
    def __init__(self, weights_path: str):
        self.model = YOLO(weights_path)

    def predict_map(self, image_path: str, conf=0.6) -> dict[str, Detection]:
        results = self.model(image_path)
        det_by_class = {}
        for r in results:
            for b in r.boxes:
                c = float(b.conf[0])
                if c >= conf:
                    cls_name = self.model.names[int(b.cls[0])]
                    x, y, w, h = b.xywh[0].tolist()
                    det_by_class[cls_name] = Detection(cls_name, int(x), int(y), int(w), int(h), c)
        return det_by_class

    def save_annot(self, results, out_path: str):
        results[0].save(filename=out_path)

    def raw(self, image_path: str):
        return self.model(image_path)
