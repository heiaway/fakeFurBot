import json
import requests
import time


# requests user agent header
E621_HEADER = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}


def get_aliases(tag):
    search_link = f"https://e621.net/tag_aliases.json?search[name_matches]={tag}"
    r = requests.get(search_link, headers=E621_HEADER)
    r.raise_for_status()
    js = json.loads(r.text)
    return js


base_tags = []
# load tags from file
with open("blacklist.txt", "r") as f:
    for line in f.read().split("\n"):
        base_tags.append(line)

full_tag_list = []
# we're getting all aliases for each tag from e621's API
for tag in base_tags:
    print(f"Getting aliases for {tag=}")
    first_js = get_aliases(tag)

    # for some reason e621 returns a special { "tag_aliases":[] }
    # when there are no aliases instead of just an empty alias list:
    if not isinstance(first_js, list):
        # so no aliases => add only tag
        full_tag_list.append(tag)
        print("Waiting 2 seconds")
        time.sleep(2)
        continue
    # this means that the tag we are searching IS an alias, so search
    # again for the base tag and aliases
    elif len(first_js) == 1:
        js = get_aliases(first_js[0]["consequent_name"])
        full_tag_list += [x["antecedent_name"] for x in js]
        full_tag_list.append(js[0]["consequent_name"])
        print("Waiting 2 seconds")
        time.sleep(2)
        continue
    # if there are many tags, then we searched the base tag
    # so add all aliases, and the tag:
    else:
        full_tag_list += [x["antecedent_name"] for x in first_js]
        full_tag_list.append(first_js[0]["consequent_name"])
    print("Waiting 2 seconds")
    time.sleep(2)
print(f"{full_tag_list=}")
print("Writing tags to generated_blacklist.txt")
with open("generated_blacklist.txt", "w", encoding="UTF-8") as f:
    f.write("\n".join(full_tag_list))
