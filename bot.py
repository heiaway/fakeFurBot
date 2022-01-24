#!/usr/bin/env python3.8
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import datetime

import praw


# this is so we can handle the 503 errors caused by Reddit's servers being awful
from prawcore.exceptions import ServerError

# load variables: client_id,client_secret,password,username,e621_username,e621_key
# config.py is just python code like `client_id = "abc123"`
import config
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

# requests user agent header
E621_HEADER = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}

# we only have to log in to e621 because otherwise
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
    logging.exception(
        "Failed to open tag lists generated_blacklist.txt, blacklist.txt, and implicated_tags.txt"
    )

# how many tags are put in the comment and minimum score
TAG_CUTOFF = 25
MIN_SCORE = 25

COMMENT_FOOTER = (
    "^^By ^^default ^^this ^^bot ^^does ^^not ^^search ^^for ^^a ^^specific ^^rating. "
    "^^You ^^can ^^limit ^^the ^^search ^^with ^^`rating:s` ^^\\(safe, ^^no ^^blacklist\\), "
    "^^`rating:q` ^^\\(questionable\\), ^^or ^^`rating:e` ^^\\(explicit\\). "
    f"^^Results ^^have ^^score ^^limit ^^of ^^{MIN_SCORE}."
    "\n"
    "\n"
    "^^I ^^am ^^a ^^bot ^^who ^^searches ^^e621 ^^based ^^on ^^given ^^tags. "
    "^^Any ^^comments ^^below ^^0 ^^score ^^will ^^be ^^removed. "
    "^^Please ^^contact ^^\\/u\\/heittoaway ^^if ^^this ^^bot ^^is ^^going ^^crazy, ^^to ^^request ^^features, "
    "^^or ^^for ^^any ^^other ^^reason. [^^Source ^^code.](https://github.com/heiaway/fakeFurBot)\n"
)


def check_comment_id(id):
    """Checks if ./comment_ids.txt contains id."""

    with open("comment_ids.txt", "r") as f:
        id_list = f.read().split("\n")
        return id in id_list


def add_comment_id(id):
    """Adds a comment id to ./comment_ids.txt."""

    with open("comment_ids.txt", "a") as f:
        f.write(f"{id}\n")


def can_process(comment):
    """
    Checks if the comment has been processed before
    so the bot doesn't reply to its own comments.
    Then checks comment for \"furbot search ??\".
    """

    if check_comment_id(comment.id) or comment.author.name.lower() == config.reddit_user.lower():
        add_comment_id(comment.id)
        return False
    # this means if all lines DO NOT have the command, skip
    if all("furbot search" not in line.lower() for line in comment.body.splitlines()):
        return False
    return True


def parse_comment(comment):
    """Parses command from the comment and removes escaped backslashes."""

    comment_body = comment.body.replace("\\", "")

    # assign regex_result as None to get around fringe case where the user inputs only furbot search and nothing else
    regex_result = None

    for line in comment_body.splitlines():
        # matches furbot search (tag1 tag2), at the start of a line,
        # with an optional u/ or /u/ at the start
        if regex := re.search(r"^.*\/?(?:u\/)?furbot search (.+)", line.lower()):
            regex_result = regex.group(1)
            # we don't want multiple matches so break out
            break

    if regex_result:
        search_tags = regex_result.split(" ")
    else:
        search_tags = []

    return search_tags


def process_comment(comment):
    """
    The actual bot.
    It will check if it can process the comment, parses tags from it and searches.
    If the search contains blacklisted tags or too many tags it will answer with some info.
    If posts were found the bot will make sure that it wasn't because of the score limit
    and if it was it will say so.

    The result is an explanation text, link to the post, a direct link,
    a small list of the tags, and a footer explaining some things.
    """
    if not can_process(comment):
        return

    print(f"processing #{comment.id}")

    search_tags = parse_comment(comment)

    # prevent bot abuse with too many tags
    is_safe = ("rating:s" in search_tags) or ("rating:safe" in search_tags)
    if (not is_safe and (len(search_tags) + len(TAG_BLACKLIST) >= 40)) or (
        is_safe and len(search_tags) > 40
    ):
        print("replying...")
        message_body = (
            f"Hello, {comment.author.name}.\n"
            "\n"
            f"There are more than {40-len(TAG_BLACKLIST) if not is_safe else 40} tags. Please try searching with fewer tags.\n"
            "\n"
            "---\n"
            "\n" + COMMENT_FOOTER
        )
        add_comment_id(comment.id)
        comment.reply(message_body)
        print("replied with too many tags")
        return

    # cancel search for blacklisted tags
    # below means (if any search tag is in the blacklist) and (search is not sfw)
    if (len(intersection := set(search_tags) & set(ALIASED_TAG_BLACKLIST)) != 0) and (not is_safe):
        print("replying...")
        message_body = (
            f"Hello, {comment.author.name}.\n"
            "\n"
            f"The following tags are blacklisted and were in your search: {', '.join(intersection)}\n"
            "\n"
            "---\n"
            "\n" + COMMENT_FOOTER
        )
        add_comment_id(comment.id)
        comment.reply(message_body)
        print(f"replied with blacklist at {datetime.now()}")
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
        tags_message = ""
    else:
        # clean up tag list from any markdown characters
        post_tag_list = [
            tag.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") for tag in post_tag_list
        ]

        tags_message = f"**^^Post ^^Tags:** ^^{', ^^'.join(post_tag_list[:TAG_CUTOFF])}"
        # if there are more than 25, add an additional message, replacing the rest
        if len(post_tag_list) > TAG_CUTOFF:
            tags_message += (
                f", **^^and ^^{len(post_tag_list) - TAG_CUTOFF + removed_tags_count} ^^more ^^tags**"
            )
        elif removed_tags_count > 0:
            tags_message += f", **^^and ^^{removed_tags_count} ^^more ^^tags**"

    # next start composing the final message
    # here we handle when the user inputs "furbot search"
    # without any tags and give an explanation for the result
    if len(search_tags) == 0:
        explanation_text = (
            "It seems that you did not input any tags in your search. "
            "Anyway, here is a random result from e621:"
        )
    else:
        explanation_text = "Here are the results for your search:"

    # escape underscores etc markdown formatting characters from search_tags
    # since we're putting them in the reply
    search_tags = [
        tag.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") for tag in search_tags
    ]

    message_body = (
        f"Hello, {comment.author.name}. {explanation_text}\n"
        "\n"
        f"{' '.join(search_tags)}\n"
        "\n"
        f"{link_text}\n"
        "\n"
        f"{tags_message}\n"
        "\n"
        "---\n"
        "\n" + COMMENT_FOOTER
    )

    print("replying...")
    comment.reply(message_body)
    add_comment_id(comment.id)
    print(f"succesfully replied at {datetime.now()}")
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
        logging.warning(
            "Caught an exception from prawcore caused by Reddit's 503 answers due to overloaded servers."
        )
        logging.info("Waiting for 300 seconds.")
        time.sleep(300)
    except Exception:
        logging.exception("Caught an unhandled exception.")
        logging.info("Waiting for 120 seconds.")
        time.sleep(120)
