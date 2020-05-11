<p align="center">
    <a href="https://github.com/UsergeTeam/Userge">
        <img src="resources/userge.png" alt="Userge">
    </a>
    <br>
    <b>Pluggable Telegram UserBot</b>
    <br>
    <a href="https://github.com/UsergeTeam/Userge#inspiration-">Inspiration</a>
    &nbsp•&nbsp
    <a href="https://github.com/UsergeTeam/Userge#features-">Features</a>
    &nbsp•&nbsp
    <a href="https://github.com/UsergeTeam/Userge#example-plugin-">Example</a>
    &nbsp•&nbsp
    <a href="https://github.com/UsergeTeam/Userge#requirements-">Requirements</a>
    &nbsp•&nbsp
    <a href="https://github.com/UsergeTeam/Userge#project-credits-">Project Credits</a>
    &nbsp•&nbsp
    <a href="https://github.com/UsergeTeam/Userge#copyright--license-">Copyright & License</a>
</p>

# Userge 🔥

> **Userge** is a Powerful , _Pluggable_ Telegram UserBot written in _Python_ using [Pyrogram](https://github.com/pyrogram/pyrogram).

## Inspiration 😇

> This project is inspired by the following projects :)

* [tg_userbot](https://github.com/watzon/tg_userbot) ( heavily ) 🤗
* [PyroGramUserBot](https://github.com/SpEcHiDe/PyroGramUserBot)
* [Telegram-Paperplane](https://github.com/RaphielGang/Telegram-Paperplane)
* [UniBorg](https://github.com/SpEcHiDe/UniBorg)

> Special Thanks to all of you !!!.

## Features 😍

* Powerful and Very Useful **built-in** Plugins
  * gdrive ( Team Drives Supported! ) 🤥
  * zip / unzip
  * telegram upload
  * telegram download
  * etc...
* Channel & Group log support
* Database support
* Build-in help support
* Easy to Setup & Use
* Easy to add / port Plugins
* Easy to write modules with the modified client

## Example Plugin 🤨

[![Codacy Badge](https://api.codacy.com/project/badge/Grade/dacadcbabdb74de3903ddae25dc95375)](https://app.codacy.com/gh/UsergeTeam/Userge?utm_source=github.com&utm_medium=referral&utm_content=UsergeTeam/Userge&utm_campaign=Badge_Grade_Dashboard)

```python
from userge import userge, Message

LOG = userge.getLogger(__name__)  # logger object

CHANNEL = userge.getCLogger(__name__)  # channel logger object

@userge.on_cmd("test", about="help text to this command")  # adding handler and help text to .test command
async def testing(message: Message):
   LOG.info("starting test command...")  # log to console

   await message.edit("testing...", del_in=5)  # this will be automatically deleted after 5 sec

   await CHANNEL.log("testing completed!")  # log to channel
```

## Requirements 🥴

* Python 3.6 or Higher 👻
* Telegram [API Keys](https://my.telegram.org/apps)
* Google Drive [API Keys](https://console.developers.google.com/)
* MongoDB [Database URL](https://cloud.mongodb.com/)

## How To Deploy 👷

* **[HEROKU](https://www.heroku.com/) Method** 🔧

  > First click the button below. 

  > If you don't have HU_STRING_SESSION just ignore it.  

  > After Deployed to Heroku first turn off the app (resources -> turn off) and run `bash genStr` in console (more -> run console).  

  > After that copy the string session and past it in Config Vars (settings -> reveal config vars). 

  > Finally turn on the app and check the logs (settings -> view logs) :)

  [![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/UsergeTeam/Userge)

* **Other Method** 🔧

  ```bash
  # clone the repo
  git clone https://github.com/UsergeTeam/Userge.git
  cd Userge

  # create virtualenv
  virtualenv -p /usr/bin/python3 venv
  . ./venv/bin/activate

  # install requirements
  pip install -r requirements.txt

  # Create config.env as given config.env.sample and fill that
  cp config.env.sample config.env

  # get string session and add it to config.env
  bash genStr

  # finally run the Userge ;)
  bash run
  ```

* **[More Detailed Guide](https://docs.google.com/document/d/15uoiOn2NkN518MMkx9h5UaMEWMp8aNZqJocXvS0uI6E)** 📝

> TODO: add Docker Support.

### Video Tutorial 🎥

  [![Tutorial](resources/tutorial.jpg)](https://youtu.be/-XJj686zeiY "Tutorial")

### Support & Discussions 👥

> Head over to the [Discussion Group](https://t.me/slbotsbugs) and [Update Channel](https://t.me/theUserge)

### Project Credits 💆‍♂️

* [Specially to these projects](https://github.com/UsergeTeam/Userge#inspiration-) 🥰
* [@uaudIth](https://t.me/uaudIth)
* [@K_E_N_W_A_Y](https://t.me/K_E_N_W_A_Y)
* [@nawwasl](https://t.me/nawwasl)
* [@THARUKA](https://t.me/TharukaN97)
* [@gotstc](https://t.me/gotstc)

### Copyright & License 👮

* Copyright (C) 2020 by [UsergeTeam](https://github.com/UsergeTeam) ❤️️
* Licensed under the terms of the [GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007](https://github.com/UsergeTeam/Userge/blob/master/LICENSE)

# Heroku aria2c

This is a fork of https://github.com/maple3142/heroku-aria2c/

Things edited here are:
1. Fixed deploy button (I saw it here: https://github.com/maple3142/heroku-aria2c/commit/d6670a2a4eab67ea1d2a344c402c5faf51616ff8) 
2. Changed the login page into a better one (see this: https://jsfiddle.net/x1u6aspb/)
3. Fixed bugs (The changes were based on: https://github.com/MrRobotGOD/heroku-aria2c)
4. Beautified AriaNg/index.php (formerly just one line, using https://www.jpkc.com/tools/beautify/)

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/sagirisayang/heroku-aria2c/tree/master)

> Do not overuse it, or your account might be banned by Heroku.

## Optionally sync downloaded file to your cloud drive with Rclone

1. Setup Rclone locally by following offical instructions: https://rclone.org/docs/
2. Find your `rclone.conf` file, it should look like this:

```conf
[DRIVENAME]
type = WHATEVER
client_id = WHATEVER
client_secret = WHATEVER
scope = WHATEVER
token = WHATEVER

others entries...
```

3. Find the drive you want to use, and copy its `type = ...` to  `... token = ...` section.
4. Replace all linebreaks with `\n`
5. Deploy with the button above, and paste that text in `RCLONE_CONFIG`
6. Set `RCLONE_DESTINATION` to a path you want to store your downloaded files.

## FAQ

### It automatically stop after 30 minutes, and files were lost.

It is because Heroku's free dyno will idle when there is no incoming request within 30 minutes, and your files will be deleted too, this is why you might want to use Rclone.

### Can I delete files?

No. Just wait for its idling, and your files will be deleted.

### You said it will idle automatically, so I can't download large files?

It will generate fake requests when there are downloading or uploading tasks, so it won't idle when your files aren't completed.

### I don't know how to setup Rclone, can you help me?

No. I thought the instructions above are enough.