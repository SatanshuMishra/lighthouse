from shelfapi.data import BOOKS
from shelfapi.dates import format_day


def list_books():
    return {
        "books": [
            {
                "id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "pages": book["pages"],
                "added": format_day(book["added"]),
            }
            for book in BOOKS
        ]
    }
