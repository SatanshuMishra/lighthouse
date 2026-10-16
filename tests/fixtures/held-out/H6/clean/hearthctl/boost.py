BOOST_SECONDS = 30 * 60


def start(link, seconds=BOOST_SECONDS):
    return link.send("BOOST {}".format(seconds))
