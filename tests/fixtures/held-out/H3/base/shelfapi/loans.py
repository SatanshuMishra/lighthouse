from shelfapi.data import LOANS
from shelfapi.dates import format_day


def list_loans():
    return {
        "loans": [
            {"id": loan["id"], "book": loan["book"], "member": loan["member"], "due": format_day(loan["due"])}
            for loan in LOANS
        ]
    }
