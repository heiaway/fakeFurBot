#!/usr/bin/env python3
import praw
import json
import time
import re
import requests
import logging

# to fix ugly multiline strings
from textwrap import dedent


# open file in current working directory, so hopefully the same as the script's directory
with open("login.txt", "r") as f:
    # file format is: client_id,client_secret,password,username
    file_info = f.read().split(",")
    # strip spaces just to be sure
    file_info = [x.strip() for x in file_info]


# log in to reddit and set subreddit
reddit = praw.Reddit(
    client_id=file_info[0],
    client_secret=file_info[1],
    password=file_info[2],
    user_agent="/r/Furry_irl bot by /u/heittoaway",
    username=file_info[3],
)
subreddit = reddit.subreddit("furry_irl")

# requests user agent header
header = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}


def check_comment_id(id):
    # opens id file "comment_ids.txt" and returns True if supplied id is in the file
    with open("comment_ids.txt", "r") as f:
        id_list = f.read().split("\n")
        return id in id_list


def add_comment_id(id):
    with open("comment_ids.txt", "a") as f:
        f.write(f"{id}\n")


def main():
    # start listening for new comments
    for comment in subreddit.stream.comments():
        # if id is not new, or the author has the same name as the bot's user, skip it.
        if (
            check_comment_id(comment.id)
            or comment.author.name.lower() == file_info[3].lower()
        ):
            add_comment_id(comment.id)
            continue
        else:
            print(f"processing #{comment.id}")

        # remove backslashes, since occasionally they will mess up searches with
        # escaped underscores: e.g. long\_tag\_thing
        comment_body = comment.body.replace("\\", "")

        # take comment text and split into lines and turn into lowercase
        text_lines = [x.lower() for x in comment.body.split("\n")]

        # then check if there's actually a command
        if all(["furbot search" not in line for line in text_lines]):
            continue

        for line in text_lines:
            # find earlier search command and get the tags
            regex = re.search(r"furbot search (.+)", line)
            # we don't need multiple matches so break out
            if regex:
                regex_result = regex.group(1)
                break

        # parse tags into list
        search_tags = regex_result.split(" ")

        # make a search link out of them, and fetch the result_json
        base_link = "https://e621.net/posts.json?tags=order%3Arandom+score%3A>19+-gore+-castration+-feces+-scat+-hard_vore"
        r = requests.get(base_link + "+" + "+".join(search_tags), headers=header)
        r.raise_for_status()
        result_json = r.text

        # parse the response json into a list of dicts, where each post is a dict
        posts = list(json.loads(result_json)["posts"])

        # create the Post | Direct link text
        if len(posts) == 0:
            # test if score was the problem by requesting another list from the site,
            # but wait for a second to definitely not hit the limit rate
            time.sleep(1)
            unscored_base_link = "https://e621.net/posts.json?tags=order%3Arandom+-gore+-castration+-feces+-scat+-hard_vore"

            # then we can make a link text without score limit
            r = requests.get(
                unscored_base_link + "+" + "+".join(search_tags), headers=header
            )
            r.raise_for_status()
            unscored_result_json = r.text

            # which we use to explain why there were no results,
            # since the bot can sometimes be confusing to use
            if len(list(json.loads(unscored_result_json)["posts"])) == 0:
                link_text = "No results found. You may have an invalid tag, or all possible results had blacklisted tags."
            else:
                link_text = "No results found. All results had a score below 20."
            tag_list = []
        else:
            # select first post
            first_post = posts[0]

            # Find url of first post. Oddly everything else has a cool direct link into it, but the json only supplies the id of the post and not the link.
            page_url = "https://e621.net/posts/" + str(first_post["id"])

            # Tags are separated into general species etc so combine them into one.
            tag_list = (
                first_post["tags"]["general"]
                + first_post["tags"]["species"]
                + first_post["tags"]["character"]
                + first_post["tags"]["copyright"]
                + first_post["tags"]["artist"]
                + first_post["tags"]["invalid"]
                + first_post["tags"]["lore"]
                + first_post["tags"]["meta"]
            )

            # Check for swf/flash first before setting direct link to full image.
            if first_post["file"]["ext"] == "swf":
                direct_link = "Direct links do not work properly with flash animations. Please check the post."
            else:
                # for some reason putting the thing below straight into the f-string is invalid syntax?
                dlink = first_post["file"]["url"]
                direct_link = f"[Direct Link]({dlink})"
            link_text = f"[Post]({page_url}) | {direct_link}"

        if len(tag_list) == 0:
            tags_message = ""
        else:
            tags_message = (
                f"\n\n**^^^^Post ^^^^Tags:** ^^^^{' ^^^^'.join(tag_list)}\n\n"
            )

        # compose the final message.
        message_body = f"""\
                        Hello, {comment.author.name}. Here are the results for your search:

                        {" ".join(search_tags)}

                        {link_text}{tags_message}

                        ---

                        I am a bot and a quick and temporary replacement for the real and original furbot. Contact \/u\/heittoaway if this bot is going crazy or for more information.\
                        """

        print("replying...")
        add_comment_id(comment.id)
        # dedent fixes the indentations from above, so the message doesn't appear as a code block
        comment.reply(dedent(message_body))
        print("succesfully replied")

        # this makes the bot wait after handling a new comment
        # it should slow down any loops and nicely prevents the bot from exceeding e621's request limit rate
        # it nicely also only works if a match was found so the bot **shouldn't** get stuck on other comments
        time.sleep(5)


print("Bot started")
# since PRAW doesn't handle the usual 503 errors caused by reddit's awful servers,
# they have to be handled manually. Additionally, whenever an error is raised, the
# stream stops, so we need this ugly wrapper:
while True:
    try:
        main()
    except praw.exceptions.APIException:
        print("Reddit most likely returned 503.")
        print("Waiting for 60 seconds.")
        time.sleep(60)
    except requests.exceptions.HTTPError as e:
        logging.exception("Caugh an HTTPError.")
        print("Waiting for 60 seconds.")
        time.sleep(60)
    except requests.RequestException as e:
        logging.exception("Caugh an exception from requests.")
        print("Waiting for 60 seconds.")
        time.sleep(60)
    except Exception as e:
        logging.exception("Caugh an unknown exception.")
        print("Waiting for 120 seconds.")
        time.sleep(120)
