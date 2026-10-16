from shelfapi.data import BOOKS, LOANS


def readable_day(day):
    return day.strftime("%a %d %b %Y")


def list_notices():
    titles = {book["id"]: book["title"] for book in BOOKS}
    return {
        "notices": [
            {
                "loan": loan["id"],
                "member": loan["member"],
                "message": "Please return {} by {}.".format(titles[loan["book"]], readable_day(loan["due"])),
            }
            for loan in LOANS
        ]
    }
