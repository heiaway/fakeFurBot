# fakeFurBot

This is \(or is supposed to be\) a reincarnation of the original Furbot\_ from /r/furry_irl. Only the base command `furbot search tag1 tag2` is supported. But that also means no unexpected spam from random e621 or e926 mentions. :^\) You can still of course search safe results by using the filter `rating:s` just
like on e621.

## Usage

0. Clone repo and `cd` to the project folder.
1. Install PRAW and Requests with `pip install praw requests`. (Optionally in a venv)
2. Edit `config.py.sample` with Reddit details for PRAW, change the user agent, and add e621 login information.
3. Run `mv config.py.sample config.py`
4. Fetch the blacklist aliases and tag implications: `python get_tag_aliases.py && python get_tag_implications.py`.
5. Run the bot. My preferred way is a small script:

   ```sh
   #! /bin/sh
   cd /home/user/fakefurbot || exit
   screen -L -Logfile /home/user/furbot.scrn -dmS furbot python3 /home/user/fakefurbot/bot.py
   ```
