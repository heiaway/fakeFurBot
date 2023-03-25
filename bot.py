#!/usr/bin/env python3.8
import logging
import random
import re
import threading
import time
from collections import defaultdict
from datetime import datetime

# load variables: client_id,client_secret,password,username,e621_username,e621_key
# config.py is just python code like `client_id = "abc123"`
import config
import praw

# this is so we can handle the 503 errors caused by Reddit's servers being awful
from prawcore.exceptions import ServerError

import deleter
import e621


def authenticate_reddit():
    """Authenticate on reddit with info from config."""

    return praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        username=config.reddit_user,
        password=config.reddit_pass,
        user_agent="/r/Furry_irl bot by /u/heittoaway",
    )


bot_reddit = authenticate_reddit()
subreddit = bot_reddit.subreddit("furry_irl")


logging.basicConfig(format="%(levelname)s:%(name)s:%(asctime)s: %(message)s")
logger = logging.getLogger("furbot")

# requests user agent header
E621_HEADER = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}

# we have to log in to e621 because otherwise
# the API will give "null" on any post's url that
# contains tags that are on the global blacklist
E621_AUTH = (config.e621_user, config.e621_pass)


# load constants:
try:
    print("Reading blacklisted tags from generated_blacklist.txt")
    with open("generated_blacklist.txt", "r") as f:
        ALIASED_TAG_BLACKLIST = f.read().split("\n")

    # this is due to e621 having a 40 tag limit, so we can't use all blacklisted tag aliases
    print("Reading base blacklist from blacklist.txt")
    with open("blacklist.txt", "r") as f:
        TAG_BLACKLIST = f.read().split("\n")

    # tag implication list
    print("Reading tag implications list from implicated_tags.txt")
    with open("implicated_tags.txt", "r") as f:
        TAG_IMPLICATIONS = defaultdict(list)
        for item in f.read().split("\n"):
            if item == "":
                break
            original, implied = item.split("%")
            TAG_IMPLICATIONS[original] += [implied]
except OSError:
    logger.exception(
        "Failed to open tag lists generated_blacklist.txt, blacklist.txt, and implicated_tags.txt"
    )

# how many tags are put in the comment and minimum score
TAG_CUTOFF = 25
MIN_SCORE = 25

UPPER_FOOTER = (
    "^^By ^^default ^^this ^^bot ^^does ^^not ^^search ^^for ^^a ^^specific ^^rating, "
    "^^but ^^you ^^can ^^do ^^so ^^with ^^`rating:s` ^^\\(safe, ^^no ^^blacklist\\), "
    "^^`rating:q` ^^\\(questionable\\), ^^or ^^`rating:e` ^^\\(explicit\\). "
    f"^^Results ^^have ^^score ^^limit ^^of ^^{MIN_SCORE}."
)

LOWER_FOOTER = (
    "^^I ^^am ^^a ^^bot ^^who ^^searches ^^e621 ^^based ^^on ^^given ^^tags. "
    "^^Any ^^comments ^^below ^^0 ^^score ^^will ^^be ^^removed. "
    "^^Please ^^contact ^^\\/u\\/heittoaway ^^if ^^this ^^bot ^^is ^^going ^^crazy, ^^to ^^request ^^features, "
    "^^or ^^for ^^any ^^other ^^reason. [^^Source ^^code.](https://github.com/heiaway/fakeFurBot)\n"
)

COMMENT_FOOTER = UPPER_FOOTER + "\n" "\n" + LOWER_FOOTER


def comment_id_processed(id):
    """Checks if ./comment_ids.txt contains id."""

    with open("comment_ids.txt", "r") as f:
        id_list = f.read().split("\n")
        return id in id_list


def add_comment_id(id):
    """Adds id to ./comment_ids.txt."""

    with open("comment_ids.txt", "a") as f:
        f.write(f"{id}\n")


def can_process(comment):
    """
    Checks if the comment id has been processed before
    and checks comment for \"furbot search ??\".
    """

    if comment_id_processed(comment.id) or comment.author.name.lower() == config.reddit_user.lower():
        add_comment_id(comment.id)
        return False
    # this means if all lines DO NOT have the command, skip
    if all("furbot search" not in line.lower() for line in comment.body.splitlines()):
        return False
    return True


def parse_comment(comment):
    """Parses command from comment and removes escaped backslashes."""

    comment_body = comment.body.replace("\\", "")

    # sometimes the user inputs only furbot search and nothing else so there is no match later
    regex_result = None

    for line in comment_body.splitlines():
        # matches furbot search (tag1 tag2), at the start of a line,
        # with an optional u/ or /u/ at the start
        if regex := re.search(r"^.*\/?(?:u\/)?furbot search (.+)", line.lower()):
            regex_result = regex.group(1)
            break

    search_tags = regex_result.split(" ") if regex_result else []
    logger.debug(search_tags)
    return search_tags


def reply(
    comment,
    explanation_text,
    search_tags=[],
    link_text="",
    tags_text="",
    explanation_is_error=False,
    greetings=True,
    upper_footer=True,
):
    """
    Reply based on a template and lots of options.
    """

    print("replying...")
    logger.info(f"replying to id {comment.id}")

    hellos = ["Hello", "Howdy", "Hi", "Hey", "Hey there"]

    # SyntaxError: f-string expression part cannot include a backslash
    # chr(10) is \n
    message_body = (
        (f"{random.choice(hellos)}, {comment.author.name}." if greetings else "")
        + f"{chr(10)+chr(10) if explanation_is_error else ' '}{explanation_text}\n"
        "\n"
        f"{' '.join(search_tags)}\n"
        "\n"
        f"{link_text}\n"
        "\n"
        f"{tags_text}\n"
        "\n"
        "---\n"
        "\n" + (UPPER_FOOTER if upper_footer else "") + LOWER_FOOTER
    )
    logger.debug(message_body)
    comment.reply(message_body)


def cancel_incorrect_search_and_reply(comment, search_tags):
    """Cancels search, replies, and returns True if necessary."""

    is_safe = ("rating:s" in search_tags) or ("rating:safe" in search_tags)
    # prevent bot abuse with too many tags
    if (not is_safe and (len(search_tags) + len(TAG_BLACKLIST) >= 40)) or (
        is_safe and len(search_tags) > 40
    ):
        explanation_text = f"There are more than {40-len(TAG_BLACKLIST) if not is_safe else 40} tags. Please try searching with fewer tags.\n"
        reply(comment, explanation_text, explanation_is_error=True)
        add_comment_id(comment.id)
        print(f"replied with too many tags to {comment.id} at {datetime.now()}")
        return True

    # cancel search for blacklisted tags
    # below means (if any search tag is in the blacklist) and (search is not sfw)
    if (len(intersection := set(search_tags) & set(ALIASED_TAG_BLACKLIST)) != 0) and (not is_safe):
        explanation_text = "The following tags are blacklisted and were in your search:"
        reply(comment, explanation_text, intersection)
        add_comment_id(comment.id)
        print(f"replied with blacklist to {comment.id} at {datetime.now()}")
        return True

    return False


def can_reply_to_good_bot(comment):
    if comment.is_root:
        return False

    parent = comment.parent()
    parent.refresh()
    if parent.author is None:
        return False

    is_reply = parent.author.name.lower() == config.reddit_user.lower()

    return is_reply and not comment_id_processed(comment.id) and "good bot" in comment.body.lower()


def good_bot_reply(comment):
    explanation_text = f"Thank you {comment.author}! I am glad I could be helpful. \\^^"
    reply(comment, explanation_text, greetings=False, upper_footer=False)
    add_comment_id(comment.id)
    print(f"replied to good bot {comment.id} at {datetime.now()}")


def process_comment(comment):
    """
    The actual bot.
    It will check if it can process the comment, parses tags and searches.
    If the search contains blacklisted tags or too many tags it will answer with some info.
    If posts were found the bot will make sure that it wasn't because of the score limit
    and if it was it will reply so.
    """

    # check if comment is a reply to the bot's comment and reply
    if can_reply_to_good_bot(comment):
        good_bot_reply(comment)
        return

    if not can_process(comment):
        return

    print(f"processing #{comment.id} at {datetime.now()}")

    search_tags = parse_comment(comment)

    if cancel_incorrect_search_and_reply(comment, search_tags):
        return

    posts = e621.search(search_tags, TAG_BLACKLIST, E621_HEADER, E621_AUTH, min_score=MIN_SCORE)

    # if no posts were found, search again to make error message more specific
    if len(posts) == 0:
        # rate-limit
        time.sleep(1)
        # re-search posts without the score limit
        posts = e621.search(search_tags, TAG_BLACKLIST, E621_HEADER, E621_AUTH, no_score_limit=True)
        # which we use to explain why there were no results,
        # since the bot can sometimes be confusing to use
        if len(posts) == 0:
            link_text = (
                "No results found. You may have an invalid e621 tag, or all possible results had blacklisted tags. "
                "The command format should be `furbot search e621_tag another_e621_tag`. Read [e621's search cheatsheet](https://e621.net/help/cheatsheet) for more info."
            )
        else:
            link_text = f"No results found. All results had a score below {MIN_SCORE}."
        post_tag_list = []
    # create the Post | Direct link text and save tags
    else:
        first_post = posts[0]

        # Find url of first post. Oddly everything else has a cool direct link into it,
        # but the json only supplies the id of the post and not the link.
        page_url = "https://e621.net/posts/" + str(first_post["id"])

        # Tags are separated into general species etc so combine them into one

        # fix tags a bit by removing implicated tags.
        # So e.g. bird implicates avian, and we probably know
        # a bird is an avian and don't need *really* the avian tag.
        post_tag_list, removed_tags_count = e621.remove_implicated_tags(
            first_post["tags"], TAG_IMPLICATIONS
        )
        # post_tag_list is still ordered based on the category order (artist, copyright, etc...)

        direct_link = f"[Direct Link]({first_post['file']['url']})"
        link_text = f"[Post]({page_url}) | {direct_link} | Score: {first_post['score']['total']}"

    # create the small tag list
    if len(post_tag_list) == 0:
        tags_text = ""
    else:
        # clean up tag list from any markdown characters
        post_tag_list = [
            tag.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") for tag in post_tag_list
        ]

        tags_text = f"**^^Post ^^Tags:** ^^{', ^^'.join(post_tag_list[:TAG_CUTOFF])}"
        # if there are more than 25, add an additional message, replacing the rest
        if len(post_tag_list) > TAG_CUTOFF:
            tags_text += (
                f", **^^and ^^{len(post_tag_list) - TAG_CUTOFF + removed_tags_count} ^^more ^^tags**"
            )
        elif removed_tags_count > 0:
            tags_text += f", **^^and ^^{removed_tags_count} ^^more ^^tags**"

    # escape underscores etc markdown formatting characters from search_tags
    # since we're putting them in the reply
    search_tags = [
        tag.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") for tag in search_tags
    ]

    # compose final message
    if "furbot" in search_tags:
        explanation_text = "\>///< Okay, I guess if you want to see me."
        reply(comment, explanation_text, search_tags, link_text, tags_text, greetings=False)
    else:
        if len(search_tags) == 0:
            explanation_text = (
                "It seems that you did not input any tags in your search. "
                "Anyway, here is a random result from e621:"
            )
        else:
            explanation_text = "Here are the results for your search:"
        reply(comment, explanation_text, search_tags, link_text, tags_text)

    add_comment_id(comment.id)
    print(f"succesfully replied to {comment.id} at {datetime.now()}")
    time.sleep(5)


# launch comment deleter in its own thread and pass its Reddit instance to it
# doesn't need a loop since it won't crash randomly
print("Creating and starting deleter_thread")
deleter_reddit = authenticate_reddit()
deleter_thread = threading.Thread(target=deleter.deleter_function, args=(deleter_reddit,), daemon=True)
deleter_thread.start()

# since PRAW doesn't handle the usual 503 errors caused by reddit's awful servers,
# they have to be handled manually. And when an error is raised, the
# stream stops, so we need this ugly wrapper:
while True:
    try:
        print(f"Starting bot at {datetime.now()}")
        for comment in subreddit.stream.comments():
            process_comment(comment)
    except ServerError:
        logger.warning(
            "Caught an exception from prawcore caused by Reddit's 503 answers due to overloaded servers."
        )
        print("Waiting for 300 seconds.")
        time.sleep(300)
    except Exception:
        logger.exception("Caught an unhandled exception.")
        print("Waiting for 120 seconds.")
        time.sleep(120)
