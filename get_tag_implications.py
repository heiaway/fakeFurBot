import time

import requests

# requests user agent header
E621_HEADER = {"User-Agent": "/r/Furry_irl FakeFurBot by reddit.com/u/heittoaway"}

base_list = []

counter = 1

print("Reading pages of tag implications with 1 second delay per read")
while True:
    print(f"page {counter}")
    search_link = (
        "https://e621.net/tag_implications.json"
        + "?commit=Search"
        + "&search%5Border%5D=name"
        + "&search%5Bstatus%5D=Active"
        + f"&limit=320&page={counter}"
    )
    r = requests.get(
        search_link,
        headers=E621_HEADER,
    )
    r.raise_for_status()
    js = r.json()

    base_list += js

    # 320 results per page means if there are fewer that
    # must be the last page
    if len(js) < 320:
        print("Done getting pages")
        break
    counter += 1
    time.sleep(1)

print("Writing tags to implicated_tags.txt")
with open("implicated_tags.txt", "w") as f:
    f.write("")
with open("implicated_tags.txt", "a") as f:
    for item in base_list:
        from_ = item["antecedent_name"]
        to = item["consequent_name"]
        # tag%implied_tag
        # because % cannot be in an e621 tag
        f.write(f"{from_}%{to}\n")
