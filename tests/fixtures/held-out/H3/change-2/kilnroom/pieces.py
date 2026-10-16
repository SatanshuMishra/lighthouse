def filled(value):
    return isinstance(value, str) and bool(value.strip())


def list_pieces(queue, params, body):
    return 200, {"pieces": queue.listed()}


def show_piece(queue, params, body):
    piece = queue.find(params["id"])
    if piece is None:
        return 404, {"error": "no piece {} in the queue".format(params["id"])}
    return 200, piece


def add_piece(queue, params, body):
    maker, title, glaze = body.get("maker"), body.get("title"), body.get("glaze", "none")
    if not (filled(maker) and filled(title) and filled(glaze)):
        return 400, {"error": "maker and title are required, and glaze must be text"}
    return 201, queue.add(maker.strip(), title.strip(), glaze.strip())


def withdraw_piece(queue, params, body):
    piece = queue.withdraw(params["id"])
    if piece is None:
        return 404, {"error": "no piece {} in the queue".format(params["id"])}
    return 200, {"withdrawn": piece}
