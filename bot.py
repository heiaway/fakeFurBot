#!/usr/bin/env python3.8
import json
import logging
import re
import threading
import time
from datetime import datetime

import praw
import requests

# this is so we can handle the 503 errors caused by Reddit's servers being awful
from prawcore.exceptions import ServerError

# open file in current working directory, so hopefully the same as the script's directory
with open("login.txt", "r") as f:
    # file format is: client_id,client_secret,password,username
    file_info = f.read().split(",")
    # strip spaces just to be sure
    file_info = [x.strip() for x in file_info]


# log in to reddit and set subreddit
bot_reddit = praw.Reddit(
    client_id=file_info[0],
    client_secret=file_info[1],
    password=file_info[2],
    user_agent="/r/Furry_irl bot by /u/heittoaway",
    username=file_info[3],
)
subreddit = bot_reddit.subreddit("furry_irl")

deleter_reddit = praw.Reddit(
    client_id=file_info[0],
    client_secret=file_info[1],
    password=file_info[2],
    user_agent="/r/Furry_irl bot by /u/heittoaway",
    username=file_info[3],
)

# change the name to be clearer since the bot's name will be used later
bot_username = file_info[3]

# requests user agent header
header = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}


def deleter_function(deleter_reddit):
    # get an Redditor instance of current user (aka the bot)
    user = deleter_reddit.user.me()
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
            # check every ~10 minutes
            time.sleep(600)
    except Exception as e:
        logging.exception("DELETER: Caught an unknown exception.")
        logging.info("DELETER: Waiting for 300 seconds before resuming")
        time.sleep(300)


def check_comment_id(id):
    # opens id file "comment_ids.txt" and returns True if supplied id is in the file
    with open("comment_ids.txt", "r") as f:
        id_list = f.read().split("\n")
        return id in id_list


def add_comment_id(id):
    with open("comment_ids.txt", "a") as f:
        f.write(f"{id}\n")


def search(search_tags, TAG_BLACKLIST, no_score_limit=False):
    # make a search link out of them, and fetch the result_json
    BASE_LINK = (
        "https://e621.net/posts.json?tags=order%3Arandom+score%3A>19" + "+-" + "+-".join(TAG_BLACKLIST)
    )
    UNSCORED_BASE_LINK = (
        "https://e621.net/posts.json?tags=order%3Arandom" + "+-" + "+-".join(TAG_BLACKLIST)
    )

    r = requests.get(
        (UNSCORED_BASE_LINK if no_score_limit else BASE_LINK) + "+" + "+".join(search_tags),
        headers=header,
    )
    r.raise_for_status()
    result_json = r.text
    print(r.text)

    # parse the response json into a list of dicts, where each post is a dict
    return list(json.loads(result_json)["posts"])


def process_comment(comment):
    # constants:
    COMMENT_FOOTER = (
        "^^By ^^default ^^this ^^bot ^^does ^^not ^^search ^^for ^^a ^^specific ^^rating. ^^You ^^can ^^limit ^^the ^^search ^^with ^^`rating:s` ^^\(safe\), ^^`rating:q` ^^\(questionable\), ^^or ^^`rating:e` ^^\(explicit\)."
        "\n"
        "\n"
        "^^I ^^am ^^a ^^bot ^^and ^^a ^^quick ^^and ^^temporary ^^replacement ^^for ^^the ^^real ^^and ^^original ^^furbot. "
        "^^Any ^^comments ^^below ^^0 ^^score ^^will ^^be ^^removed. "
        "^^Please ^^contact ^^\/u\/heittoaway ^^if ^^this ^^bot ^^is ^^going ^^crazy ^^or ^^for ^^more ^^information.\n"
    )
    TAG_BLACKLIST = [
        "gore",
        "castration",
        "feces",
        "poop",
        "scat",
        "hard_vore",
        "cub",
        "urine",
        "pee",
        "watersports",
        "child",
        "loli",
        "shota",
        "infestation",
    ]
    # if id is not new (=the bot has replied to it), or the author has the same name as the bot's user, skip it.
    if check_comment_id(comment.id) or comment.author.name.lower() == bot_username.lower():
        add_comment_id(comment.id)
        return

    # remove backslashes, since occasionally they will mess up searches with
    # escaped underscores: e.g. long\_tag\_thing
    comment_body = comment.body.replace("\\", "")

    # take comment text and split into lines
    text_lines = comment_body.split("\n")

    # then check if there's actually a command
    # this means if all lines DO NOT have the command, skip.
    if all(["furbot search" not in line.lower() for line in text_lines]):
        return

    print(f"processing #{comment.id}")
    # assign regex_result as None to get around fringe case where the user inputs only furbot search and nothing else
    regex_result = None
    for line in text_lines:
        # find earlier search command and get the tags
        regex = re.search(r"furbot search (.+)", line.lower())
        # we don't need multiple matches so break out
        if regex:
            regex_result = regex.group(1)
            break

    # parse tags into list
    if regex_result:
        search_tags = regex_result.split(" ")
    else:
        search_tags = []

    # prevent bot abuse with too many tags
    if len(search_tags) >= 20:
        print("replying...")
        message_body = (
            f"Hello, {comment.author.name}.\n"
            "\n"
            f"There are more than 20 tags. Please try searching with fewer tags.\n"
            "\n"
            "---\n"
            "\n" + COMMENT_FOOTER
        )
        add_comment_id(comment.id)
        comment.reply(message_body)
        print("replied with too many tags")
        return
    # cancel search for blacklisted tags
    # if any search tag is in the blacklist
    if len(intersection := set(search_tags) & set(TAG_BLACKLIST)) != 0:
        print("replying...")
        message_body = (
            f"Hello, {comment.author.name}.\n"
            "\n"
            f"The following tags are blacklisted and were in your search: {' '.join(intersection)}\n"
            "\n"
            "---\n"
            "\n" + COMMENT_FOOTER
        )
        add_comment_id(comment.id)
        comment.reply(message_body)
        print("replied with blacklist")
        return

    posts = search(search_tags, TAG_BLACKLIST)

    # create the Post | Direct link text
    # if no posts were found, search again to make error message more specific
    if len(posts) == 0:
        # test if score was the problem by requesting another list from the site,
        # but wait for a second to definitely not hit the limit rate
        time.sleep(1)
        # re-search posts without the score limit
        posts = search(search_tags, TAG_BLACKLIST, no_score_limit=True)
        # which we use to explain why there were no results,
        # since the bot can sometimes be confusing to use
        if len(posts) == 0:
            link_text = "No results found. You may have an invalid tag, or all possible results had blacklisted tags."
        else:
            link_text = "No results found. All results had a score below 20."
        tag_list = []
    # and if posts were found, process the first one
    else:
        # select first post
        first_post = posts[0]

        # Find url of first post. Oddly everything else has a cool direct link into it, but the json only supplies the id of the post and not the link.
        page_url = "https://e621.net/posts/" + str(first_post["id"])

        # Tags are separated into general species etc so combine them into one.
        tag_list = (
            first_post["tags"]["artist"]
            + first_post["tags"]["copyright"]
            + first_post["tags"]["character"]
            + first_post["tags"]["species"]
            + first_post["tags"]["general"]
            + first_post["tags"]["lore"]
            + first_post["tags"]["meta"]
        )

        # Check for swf/flash first before setting direct link to full image.
        if first_post["file"]["ext"] == "swf":
            direct_link = (
                "Direct links do not work properly with flash animations. Please check the post."
            )
        else:
            direct_link = f"[Direct Link]({first_post['file']['url']})"
        link_text = f"[Post]({page_url}) | {direct_link}"

    # create the small tag list
    if len(tag_list) == 0:
        tags_message = ""
    else:
        # combine first tag_cutoff amount of tags into the small message and
        # replace "_" and similar characters in the tag list with escaped ones (e.g. "\_") to avoid Reddit's markup
        TAG_CUTOFF = 25
        # clean up tag list from markdown characters
        tag_list = [tag.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") for tag in tag_list]
        tags_message = f"**^^Post ^^Tags:** ^^{' ^^'.join(tag_list[:TAG_CUTOFF])}"
        # if there are more than 25, add an additional message
        if len(tag_list) > TAG_CUTOFF:
            tags_message += f" **^^and ^^{len(tag_list) - TAG_CUTOFF} ^^more ^^tags**"

    # compose the final message
    # here we handle a fringe case where the user inputs "furbot search" without any tags and give an explanation for the result
    if len(search_tags) == 0:
        explanation_text = "It seems that you did not input any tags in your search. Anyway, here is a random result from e621:"
    else:
        explanation_text = "Here are the results for your search:"

    # fix underscores etc markdown formatting characters from search_tags
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

    # this makes the bot wait after handling a new comment
    # it should slow down any loops and nicely prevents the bot from exceeding e621's request limit rate
    # it nicely also only works if a match was found so the bot **shouldn't** get stuck on other comments
    time.sleep(5)


def wrapper():
    # start listening for new comments
    for comment in subreddit.stream.comments():
        process_comment(comment)


# launch comment deleter in its own thread and pass its Reddit instance to it
print("Creating and starting deleter_thread")
deleter_thread = threading.Thread(target=deleter_function, args=(deleter_reddit,), daemon=True)
deleter_thread.start()

print("Bot started")
# since PRAW doesn't handle the usual 503 errors caused by reddit's awful servers,
# they have to be handled manually. Additionally, whenever an error is raised, the
# stream stops, so we need this ugly wrapper:
# This might have been changed in a recent PRAW update, but I'm not exactly sure if it works so this can stay
while True:
    try:
        print(f"Starting at {datetime.now()}")
        wrapper()
    except praw.exceptions.RedditAPIException:
        logging.exception("Caught a Reddit API error.")
        logging.info("Waiting for 60 seconds.")
        time.sleep(60)
    except requests.exceptions.HTTPError:
        logging.exception("Caught an HTTPError.")
        logging.info("Waiting for 60 seconds.")
        time.sleep(60)
    except requests.RequestException:
        logging.exception("Caught an exception from requests.")
        logging.info("Waiting for 60 seconds.")
        time.sleep(60)
    except ServerError:
        logging.warning(
            "Caught an exception from prawcore caused by Reddit's 503 answers due to overloaded servers."
        )
        logging.info("Waiting for 300 seconds.")
        time.sleep(300)
    except Exception:
        logging.exception("Caught an unknown exception.")
        logging.info("Waiting for 120 seconds.")
        time.sleep(120)
