from datetime import date

BOOKS = (
    {"id": 1, "title": "Dune", "author": "Frank Herbert", "pages": 412, "added": date(2023, 11, 2)},
    {"id": 2, "title": "The Left Hand of Darkness", "author": "Ursula K. Le Guin", "pages": 304, "added": date(2024, 1, 15)},
    {"id": 3, "title": "Kindred", "author": "Octavia E. Butler", "pages": 264, "added": date(2024, 2, 20)},
)

LOANS = (
    {"id": 1, "book": 1, "member": "ana", "due": date(2024, 3, 5)},
    {"id": 2, "book": 3, "member": "kwame", "due": date(2024, 3, 12)},
)
