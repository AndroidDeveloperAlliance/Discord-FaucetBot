# Universal Faucet Bot

Dircord Faucet Bot is an open source, free to use faucet bot for discord.

Forked from a nano tip bot based tip bot and intended to use as an add on to tip bots based on a similar source.

This faucet bot is still a very early version and there are a lot of enhancements to come.

## Usage

To run the bot, update `settings.py` and `faucet_settings.py` with wallet ID and discord bot ID+Token and other parameters, then simply use:

```
python3 bot.py
```

or to run in background

```
nohup python3 bot.py &
```

## Dependencies (install using pip)

- Python 3.5+
- Wallet Node v10+
- `setuptools`
- `discord`
- `peewee`
- `asyncio`
- `pycurl`

## Disclaimer

FaucetBot for Discord.
FaucetBot is still in beta testing and should be used for fun, at your own risk. Bugs may arise and we will fix them asap but we cannot refund any losses or invalid TX's. 
