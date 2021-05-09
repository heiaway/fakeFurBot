#!/usr/bin/env python3.8
import json
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import datetime

import praw
import requests

# this is so we can handle the 503 errors caused by Reddit's servers being awful
from prawcore.exceptions import ServerError

# load variables: client_id,client_secret,password,username,e621_username,e621_key
# config.py is just python code like `client_id = "abc123"`
import config


def authenticate_reddit():
    return praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        username=config.reddit_user,
        password=config.reddit_pass,
        user_agent="/r/Furry_irl bot by /u/heittoaway",
    )


bot_reddit = authenticate_reddit()
subreddit = bot_reddit.subreddit("furry_irl")

# change the name to be clearer since the bot's name will be used later
# bot_username = file_info[3]

# requests user agent header
E621_HEADER = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}

# we have to log in to e621 since otherwise
# the API will give "null" on any post's url that
# contains tags that are on the global blacklist
e621_auth = (config.e621_user, config.e621_pass)

# constants:
COMMENT_FOOTER = (
    "^^By ^^default ^^this ^^bot ^^does ^^not ^^search ^^for ^^a ^^specific ^^rating. "
    "^^You ^^can ^^limit ^^the ^^search ^^with ^^`rating:s` ^^\(safe, ^^no ^^blacklist\), ^^`rating:q` ^^\(questionable\), ^^or ^^`rating:e` ^^\(explicit\). "
    "^^Results ^^have ^^score ^^limit ^^of ^^20."
    "\n"
    "\n"
    "^^I ^^am ^^a ^^bot ^^and ^^a ^^replacement ^^for ^^the ^^realer ^^and ^^original ^^furbot. "
    "^^Any ^^comments ^^below ^^0 ^^score ^^will ^^be ^^removed. "
    "^^Please ^^contact ^^\/u\/heittoaway ^^if ^^this ^^bot ^^is ^^going ^^crazy, ^^to ^^request ^^features, ^^or ^^for ^^any ^^other ^^reasons. [^^Source  ^^code.](https://github.com/vaisest/fakeFurBot)\n"
)

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

# how many tags are put in the comment
TAG_CUTOFF = 25


def deleter_function(deleter_reddit):
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
                # check every ~10 minutes
                time.sleep(600)
        except Exception:
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


def can_process(comment):
    # if id is not new (i.e. the bot has replied to it), or the author has the same name as the bot's user, skip it.
    if check_comment_id(comment.id) or comment.author.name.lower() == config.reddit_user.lower():
        add_comment_id(comment.id)
        return False
    # then check if there's actually a command
    # this means if all lines DO NOT have the command, skip
    if all("furbot search" not in line.lower() for line in comment.body.splitlines()):
        return False
    return True


def parse_comment(comment):
    # remove backslashes, since occasionally they will mess up searches with
    # escaped underscores: e.g. long\_tag\_thing to avoid italics
    comment_body = comment.body.replace("\\", "")

    # assign regex_result as None to get around fringe case where the user inputs only furbot search and nothing else
    regex_result = None

    for line in comment_body.splitlines():
        regex = re.search(r"furbot search (.+)", line.lower())
        # we don't need multiple matches so break out
        if regex:
            regex_result = regex.group(1)
            break

    if regex_result:
        search_tags = regex_result.split(" ")
    else:
        search_tags = []

    return search_tags


def remove_implicated_tags(original_tags):
    original_tags = set(original_tags)
    unnecessary_tags = set()

    for tag in original_tags:
        if tag in TAG_IMPLICATIONS:
            unnecessary_tags.update(TAG_IMPLICATIONS[tag])

    return sorted(original_tags - unnecessary_tags), len(original_tags & unnecessary_tags)


def search(search_tags, TAG_BLACKLIST, no_score_limit=False):
    BASE_LINK = "https://e621.net/posts.json?tags=order%3Arandom+score%3A>19"
    UNSCORED_BASE_LINK = "https://e621.net/posts.json?tags=order%3Arandom"
    # determine if the search is guaranteed to be sfw or not
    is_safe = ("rating:s" in search_tags) or ("rating:safe" in search_tags)

    # choose which base link to use based on no_score_limit
    search_link = UNSCORED_BASE_LINK if no_score_limit else BASE_LINK
    # if the link can contain NSFW results, we add the blacklist
    if not is_safe:
        search_link += "+-" + "+-".join(TAG_BLACKLIST)
    # and in both cases we add the search cases (obviously)
    search_link += "+" + "+".join(search_tags)

    r = requests.get(
        search_link,
        headers=E621_HEADER,
        auth=e621_auth,
    )
    r.raise_for_status()
    result_json = r.text

    # parse the response json into a list of dicts, where each post is a dict
    return list(json.loads(result_json)["posts"])


def process_comment(comment):
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
            f"The following tags are blacklisted and were in your search: {' '.join(intersection)}\n"
            "\n"
            "---\n"
            "\n" + COMMENT_FOOTER
        )
        add_comment_id(comment.id)
        comment.reply(message_body)
        print(f"replied with blacklist at {datetime.now()}")
        return

    posts = search(search_tags, TAG_BLACKLIST)

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
        post_tag_list = []
    # create the Post | Direct link text and save tags
    else:
        first_post = posts[0]

        # Find url of first post. Oddly everything else has a cool direct link into it, but the json only supplies the id of the post and not the link.
        page_url = "https://e621.net/posts/" + str(first_post["id"])

        # Tags are separated into general species etc so combine them into one

        # fix tags a bit by removing implicated tags.
        # So e.g. bird implicates avian, and we probably know
        # a bird is an avian and don't need *really* the avian tag.
        removed_tags_count = 0
        post_tag_list = []

        for category in ["artist", "copyright", "character", "species", "lore", "general", "meta"]:
            result, count = remove_implicated_tags(first_post["tags"][category])
            post_tag_list += result
            removed_tags_count += count

        # Check for swf/flash first before setting direct link to full image.
        if first_post["file"]["ext"] == "swf":
            direct_link = "Flash animation. Check the post."
        else:
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
        tags_message = f"**^^Post ^^Tags:** ^^{' ^^'.join(post_tag_list[:TAG_CUTOFF])}"
        # if there are more than 25, add an additional message, replacing the rest
        if len(post_tag_list) > TAG_CUTOFF:
            tags_message += (
                f" **^^and ^^{len(post_tag_list) - TAG_CUTOFF + removed_tags_count} ^^more ^^tags**"
            )
        elif removed_tags_count > 0:
            tags_message += f" **^^and ^^{removed_tags_count} ^^more ^^tags**"

    # next start composing the final message
    # here we handle a fringe case where the user inputs "furbot search"
    # without any tags and give an explanation for the result
    if len(search_tags) == 0:
        explanation_text = "It seems that you did not input any tags in your search. Anyway, here is a random result from e621:"
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


def wrapper():
    # start listening for new comments
    for comment in subreddit.stream.comments():
        process_comment(comment)


# launch comment deleter in its own thread and pass its Reddit instance to it
print("Creating and starting deleter_thread")
deleter_reddit = authenticate_reddit()
deleter_thread = threading.Thread(target=deleter_function, args=(deleter_reddit,), daemon=True)
deleter_thread.start()


# since PRAW doesn't handle the usual 503 errors caused by reddit's awful servers,
# they have to be handled manually. Additionally, whenever an error is raised, the
# stream stops, so we need this ugly wrapper:
# This might have been changed in a recent PRAW update, but I'm not exactly sure if it works so this can stay
while True:
    try:
        print(f"Starting bot at {datetime.now()}")
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
