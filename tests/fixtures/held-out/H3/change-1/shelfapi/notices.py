from shelfapi.data import BOOKS, LOANS
from shelfapi.dates import format_day


def list_notices():
    titles = {book["id"]: book["title"] for book in BOOKS}
    return {
        "notices": [
            {
                "loan": loan["id"],
                "member": loan["member"],
                "message": "Please return {} by {}.".format(titles[loan["book"]], format_day(loan["due"])),
            }
            for loan in LOANS
        ]
    }
