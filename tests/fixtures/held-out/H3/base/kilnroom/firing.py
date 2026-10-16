import threading

SAMPLE_PIECES = (
    {"id": 1, "maker": "Ines", "title": "Celadon tea bowl", "glaze": "celadon"},
    {"id": 2, "maker": "Tomas", "title": "Lidded jar", "glaze": "tenmoku"},
    {"id": 3, "maker": "Priya", "title": "Bud vase", "glaze": "none"},
)


class FiringQueue:
    def __init__(self, pieces=SAMPLE_PIECES):
        self.pieces = tuple(dict(piece) for piece in pieces)
        self.lock = threading.Lock()

    def listed(self):
        return [dict(piece) for piece in self.pieces]

    def find(self, piece_id):
        return next((dict(piece) for piece in self.pieces if str(piece["id"]) == piece_id), None)

    def add(self, maker, title, glaze):
        with self.lock:
            piece = {"id": max((item["id"] for item in self.pieces), default=0) + 1, "maker": maker, "title": title, "glaze": glaze}
            self.pieces = self.pieces + (piece,)
        return dict(piece)
