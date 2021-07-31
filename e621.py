import json

import requests


def remove_implicated_tags(post_tags, tag_implications_list):
    """
    Removes implicated tags from the tags in a post and preserves category order.
    Takes the list of tag lists from an e621 post as an argument.
    deimplicate does the actual removing.
    """
    removed_tags_count = 0
    post_tag_list = []

    for category in ["artist", "copyright", "character", "species", "lore", "general", "meta"]:
        result, count = deimplicate(post_tags[category], tag_implications_list)
        post_tag_list += result
        removed_tags_count += count
    return post_tag_list, removed_tags_count


def deimplicate(original_tags, tag_implications_list):
    """
    Uses the tag implications to remove them
    so only the most specific tag remains.
    """

    original_tags = set(original_tags)
    unnecessary_tags = set()

    for tag in original_tags:
        if tag in tag_implications_list:
            unnecessary_tags.update(tag_implications_list[tag])

    return sorted(original_tags - unnecessary_tags), len(original_tags & unnecessary_tags)


def search(search_tags, tag_blacklist, e621_header, e621_auth, no_score_limit=False, min_score=0):
    """
    Searches on e621 and returns a list of dicts.
    Applies a blacklist if the search is NSFW.
    no_score_limit removes the score limit from the search.
    """

    base_link = f"https://e621.net/posts.json?tags=order%3Arandom+score%3A>={min_score}"
    unscored_base_link = "https://e621.net/posts.json?tags=order%3Arandom"
    # determine if the search is guaranteed to be sfw or not
    is_safe = ("rating:s" in search_tags) or ("rating:safe" in search_tags)

    # choose which base link to use based on no_score_limit
    search_link = unscored_base_link if no_score_limit else base_link

    if not is_safe:
        search_link += "+-" + "+-".join(tag_blacklist)
    # and in both cases we add the search cases (obviously)
    search_link += "+" + "+".join(search_tags)

    result = requests.get(
        search_link,
        headers=e621_header,
        auth=e621_auth,
    )
    result.raise_for_status()

    # parse the response json into a list of dicts, where each post is a dict
    return list(json.loads(result.text)["posts"])
