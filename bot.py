#!/usr/bin/env python3
import praw
import json
import time
import re
import requests


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


def search_url(tags):
    # blacklist = []
    base_url = "https://e621.net/posts.json?tags=order%3Arandom+score%3A>25"
    url = base_url + "+" + "+".join(tags)


print("bot started")
# start listening for new comments
for comment in subreddit.stream.comments(skip_existing=True):
    print(f"processing #{comment.id}")
    # if id is not new, skip it. Technically this shouldn't be necessary since we're skipping existing, but whatever
    if (
        check_comment_id(comment.id)
        or comment.author.name.lower() == file_info[3].lower()
    ):
        continue
    else:
        add_comment_id(comment.id)

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
    base_link = "https://e621.net/posts.json?tags=order%3Arandom+score%3A>25+-gore+-castration+-feces+-scat+-hard_vore"
    result_json = requests.get(
        base_link + "+" + "+".join(search_tags), headers=header
    ).text

    # parse the response json into a list of dicts, where each post is a dict
    posts = list(json.loads(result_json)["posts"])

    # create the Post | Direct link text
    if len(posts) == 0:
        link_text = "No results found. You may have an invalid tag, or all results have a score below 25."
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
        tags_message = f"\n\n**^^^^Post ^^^^Tags:** ^^^^{' ^^^^'.join(tag_list)}\n\n"

    # compose the final message.
    # yes multiline strings are very ugly, and I don't want to clean it up yet
    message_body = f"""
Hello, {comment.author.name}. Here are the results for your search:

{" ".join(search_tags)}

{link_text}{tags_message}

---


I am a bot and a quick and temporary replacement for the real and original furbot. Contact \/u\/heittoaway if this bot is going crazy or for more information.
"""

    print("replying...")
    comment.reply(message_body)
    print(" succesful\n")

    # this makes the bot wait after handling a new comment
    # it should slow down any loops and nicely prevents the bot from exceeding e621's request limit rate
    # it nicely also only works if a match was found so the bot **shouldn't** get stuck on other comments
    time.sleep(5)
