import logging
import time
from datetime import datetime


def deleter_function(deleter_reddit):
    """Function that deletes the bot's comments below 0 score on a 10 minute loop."""

    user = deleter_reddit.user.me()
    # as usual the PRAW stream error problem needs a loop:
    while True:
        try:
            print(f"DELETER: Starting deleter at {datetime.now()}")
            while True:
                # the first 200 comments ought to be enough, and should
                # limit the amount of time spent on this simple task
                comments = user.comments.new(limit=200)
                for comment in comments:
                    if comment.score < 0:
                        print(
                            f"DELETER: Removing comment #{comment.id} at {datetime.now()} due to its low score ({comment.score})."
                        )
                        print(f"'{comment.body}'")
                        comment.delete()
                # check every ~30 minutes
                time.sleep(1800)
        except Exception:
            logging.exception("DELETER: Caught an unknown exception.")
            logging.info("DELETER: Waiting for 10 minutes before resuming")
            time.sleep(600)
