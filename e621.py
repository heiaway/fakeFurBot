import json

import requests


def remove_implicated_tags_from_post(post_tags, TAG_IMPLICATIONS):
    """
    Helper function that removes implicated tags from the tags in a post one category at a time.
    E621 includes implicated tags (e.g. cat implies feline) in the tags
    and they are unnecessary.
    remove_implicated_tags does the actual removing.
    Tags are processed by category to preserve the category order.
    """
    removed_tags_count = 0
    post_tag_list = []

    for category in ["artist", "copyright", "character", "species", "lore", "general", "meta"]:
        result, count = remove_implicated_tags(post_tags[category], TAG_IMPLICATIONS)
        post_tag_list += result
        removed_tags_count += count
    return post_tag_list, removed_tags_count


def remove_implicated_tags(original_tags, TAG_IMPLICATIONS):
    """
    This function uses the tag implications from the
    implicated_tags.txt file to remove them so that only the most specific tag remains.
    """

    original_tags = set(original_tags)
    unnecessary_tags = set()

    for tag in original_tags:
        if tag in TAG_IMPLICATIONS:
            unnecessary_tags.update(TAG_IMPLICATIONS[tag])

    return sorted(original_tags - unnecessary_tags), len(original_tags & unnecessary_tags)


def search(search_tags, TAG_BLACKLIST, E621_HEADER, E621_AUTH, no_score_limit=False):
    """
    Performs a search on e621 and returns the posts in a list of dicts.
    Applies a blacklist if the search is determined to be NSFW.
    no_score_limit can remove the score limit from the search.
    """

    BASE_LINK = "https://e621.net/posts.json?tags=order%3Arandom+score%3A>19"
    UNSCORED_BASE_LINK = "https://e621.net/posts.json?tags=order%3Arandom"
    # determine if the search is guaranteed to be sfw or not
    is_safe = ("rating:s" in search_tags) or ("rating:safe" in search_tags)

    # choose which base link to use based on no_score_limit
    search_link = UNSCORED_BASE_LINK if no_score_limit else BASE_LINK

    if not is_safe:
        search_link += "+-" + "+-".join(TAG_BLACKLIST)
    # and in both cases we add the search cases (obviously)
    search_link += "+" + "+".join(search_tags)

    r = requests.get(
        search_link,
        headers=E621_HEADER,
        auth=E621_AUTH,
    )
    r.raise_for_status()
    result_json = r.text

    # parse the response json into a list of dicts, where each post is a dict
    return list(json.loads(result_json)["posts"])
