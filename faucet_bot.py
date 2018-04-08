import discord
import threading
from threading import Thread
from queue import Queue
import atexit
import time
import collections
import random
import re
import errno
import asyncio
import uuid
import datetime

import wallet
import util
# for wallet id
import settings
# for everything else
import faucet_settings
# for request table
import faucet_db
# for everything else
import db

logger = util.get_logger("main")

BOT_VERSION = "1.6"


# Minimum Amount for !rain
DAILY_MAX = faucet_settings.daily_max
# Minimum amount for !startgiveaway
DAILY_WAIT = faucet_settings.daily_wait
# Spam Threshold (Seconds) - how long to output certain commands (e.g. bigtippers)
SPAM_THRESHOLD=60
# MAX TX_Retries - If wallet does not indicate a successful send for whatever reason, retry this many times
MAX_TX_RETRIES=3
# Change command prefix to whatever you want to begin commands with
COMMAND_PREFIX=faucet_settings.command_prefix
# Withdraw Check Job - checks for completed withdraws at this interval
WITHDRAW_CHECK_JOB=15

# Create discord client
client = discord.Client()


### Response Templates ###
COMMAND_NOT_FOUND="I don't understand what you're saying, try %shelp" % COMMAND_PREFIX
HELP_INFO="%shelp:\n Display this message" % (COMMAND_PREFIX)
DEPOSIT_INFO=("%sdeposit or %sdonate:\n Displays the deposit address of the bot:") % (COMMAND_PREFIX, COMMAND_PREFIX)
WITHDRAW_INFO=("%sdailies or %sfaucet:\n Withdraws 1/4 of your daily faucet requests to the specified address") % (COMMAND_PREFIX, COMMAND_PREFIX)
DEV_INFO=("BananoFaucetBot v%s - An open source faucet bot for Discord\n" +
		"Developed by <@363689341257515019> - Feel free to send suggestions, ideas, and/or tips\n")
HELP_TEXT_1=("Faucet Commands:\n" +
		"```" +
		HELP_INFO + "\n\n" +
		DEPOSIT_INFO + "\n\n" +
		WITHDRAW_INFO + "\n\n" +
		DEV_INFO + "\n\n" +
		"```")

DEPOSIT_TEXT="The faucet wallet address is:"
DEPOSIT_TEXT_2="%s"
DEPOSIT_TEXT_3="QR: %s"
WITHDRAW_SUCCESS_TEXT="Faucet Withdraw has been queued for processing, I'll send you a link to the transaction after I've broadcasted it to the network!"
WITHDRAW_PROCESSED_TEXT="Withdraw processed:\nTransaction: https://vault.banano.co.in/transaction/%s"
FAUCET_DRY="The faucet has run dry =("
WITHDRAW_ADDRESS_NOT_FOUND_TEXT="Usage:\n```" + WITHDRAW_INFO + "```"
WITHDRAW_INVALID_ADDRESS_TEXT="Withdraw address is not valid"
WITHDRAW_ERROR_TEXT="Something went wrong ! :thermometer_face: "
STATS_ACCT_NOT_FOUND_TEXT="I could not find an account for you, try private messaging me `%sregister`" % COMMAND_PREFIX
SET_TOTAL_USAGE="Usage:\n```" + SETTIP_INFO + "```"
SET_COUNT_USAGE="Usage:\n```" + SETCOUNT_INFO + "```"
PAUSE_MSG="All transaction activity is currently suspended. Check back later."
BAN_SUCCESS="User %s can no longer receive dailies"
BAN_DUP="User %s is already banned"
UNBAN_SUCCESS="User %s has been unbanned"
UNBAN_DUP="User %s is not banned"
NOT_ELIGIBLE = "You are not eligible to withdraw from the Faucet. Conditions are 4 max daily requests, min 1 hour wait between requests and account age min. 30 days"
### END Response Templates ###

# Paused flag, indicates whether or not bot is paused
paused = False

# Thread to process send transactions
# Queue is used to communicate back to main thread
withdrawq = Queue()
class SendProcessor(Thread):
	def __init__(self):
		super(SendProcessor, self).__init__()
		self._stop_event = threading.Event()

	def run(self):
		while True:
			# Just so we don't constantly berate the database if there's no TXs to chew through
			time.sleep(10)
			txs = db.get_unprocessed_transactions()
			for tx in txs:
				if self.stopped():
					break
				source_address = tx['source_address']
				to_address = tx['to_address']
				amount = tx['amount']
				uid = tx['uid']
				attempts = tx['attempts']
				raw_withdraw_amt = str(amount) + '00000000000000000000000000000'
				wallet_command = {
					'action': 'send',
					'wallet': settings.wallet,
					'source': source_address,
					'destination': to_address,
					'amount': int(raw_withdraw_amt),
					'id': uid
				}
				src_usr = db.get_user_by_wallet_address(source_address)
				trg_usr = db.get_user_by_wallet_address(to_address)
				source_id=None
				target_id=None
				pending_delta = int(amount) * -1
				if src_usr is not None:
					source_id=src_usr.user_id
				if trg_usr is not None:
					target_id=trg_usr.user_id
				db.mark_transaction_sent(uid, pending_delta, source_id, target_id)
				logger.debug("RPC Send")
				try:

					wallet_output = wallet.communicate_wallet(wallet_command)
				except Exception as e:
					logger.exception(e)
					continue
				logger.debug("RPC Response")
				if 'block' in wallet_output:
					txid = wallet_output['block']
					db.mark_transaction_processed(uid, txid)
					logger.info('TX processed. UID: %s, TXID: %s', uid, txid)
					if target_id is None:
						withdrawq.put({'user_id':source_id, 'txid':txid})
				else:
					# Not sure what happen but we'll retry a few times
					if attempts >= MAX_TX_RETRIES:
						logger.info("Max Retires Exceeded for TX UID: %s", uid)
						db.mark_transaction_processed(uid, invalid)
					else:
						db.inc_tx_attempts(uid)
			if self.stopped():
				break

	def stop(self):
		self._stop_event.set()

	def stopped(self):
		return self._stop_event.is_set()

# Start bot, print info
sp = SendProcessor()

def handle_exit():
	sp.stop()

@client.event
async def on_ready():
	logger.info("Faucet Bot v%s started", BOT_VERSION)
	logger.info("Discord.py API version %s", discord.__version__)
	logger.info("Name: %s", client.user.name)
	logger.info("ID: %s", client.user.id)
	await client.change_presence(game=discord.Game(name=faucet_settings.playing_status))
	logger.info("Starting SendProcessor Thread")
	if not sp.is_alive():
		sp.start()
	logger.info("Registering atexit handler")
	atexit.register(handle_exit)
	logger.info("Starting withdraw check job")
	asyncio.get_event_loop().create_task(check_for_withdraw())
	logger.info("Continuing outstanding giveaway")
	asyncio.get_event_loop().create_task(start_giveaway_timer())

async def check_for_withdraw():
	try:
		await asyncio.sleep(WITHDRAW_CHECK_JOB)
		asyncio.get_event_loop().create_task(check_for_withdraw())
		while not withdrawq.empty():
			withdraw = withdrawq.get(block=False)
			if withdraw is None:
				continue
			user_id = withdraw['user_id']
			txid = withdraw['txid']
			user = await client.get_user_info(user_id)
			await post_dm(user, WITHDRAW_PROCESSED_TEXT, txid)
	except Exception as ex:
		logger.exception(ex)

# Command List
commands=['help', 'deposit', 'dailies', 'faucet', 'donate', 'faucetban', 'faucetunban']
cmdlist=[COMMAND_PREFIX + c for c in commands]

# Override on_message and do our spam check here
nickname_set = False
@client.event
async def on_message(message):
	global paused,nickname_set

#	if not nickname_set and settings.discord_bot_name is not None:
#		bot_member = message.server.get_member(client.user.id)
#		await client.change_nickname(bot_member, settings.discord_bot_name)
#		nickname_set = True

	# disregard messages sent by our own bot
	if message.author.id == client.user.id:
		return

	if db.last_msg_check(message.author.id, message.content, message.channel.is_private) == False:
		return

	# Make sure cmd is supported
	content = message.content
	if len(content.split()) >= 1:
		cmd = message.content.split(' ', 1)[0]
	else:
		return
	if cmd not in cmdlist:
		if message.channel.is_private:
			await post_response(message, COMMAND_NOT_FOUND)
		return
	# Strip prefix from command
	cmd = cmd[1:]
	if cmd == 'help':
		await help(message)
	elif cmd == 'tipunban' and has_admin_role(message.author.roles):
		await tipunban(message)
	elif cmd == 'pause' and has_admin_role(message.author.roles):
		paused = True
	elif cmd == 'unpause' and has_admin_role(message.author.roles):
		paused = False
	elif cmd == 'deposit' or cmd == 'register':
		await deposit(message)
	elif paused:
		await post_dm(message.author, PAUSE_MSG)
		return
	elif cmd == 'dailies' or cmd == 'faucet':
		await dailies(message)


def has_admin_role(roles):
	for r in roles:
		if r.name in faucet_settings.admin_roles:
			return True
	return False

### Commands
async def help(message):
	if message.channel.is_private:
		# Four messages because discord API responds in error with our really long help text
		await post_response(message, HELP_TEXT_1, BOT_VERSION)


async def deposit(message):
	if message.channel.is_private:
		botuser = await wallet.create_or_fetch_user(faucet_settings.discord_bot_id)
		botuser_deposit_address = botuser.wallet_address
		await post_response(message, DEPOSIT_TEXT)
		await post_response(message, DEPOSIT_TEXT_2, botuser_deposit_address)
		await post_response(message, DEPOSIT_TEXT_3, get_qr_url(botuser_deposit_address))

async def dailies(message):
	if message.channel.is_private:
		try:
			## check for join date
			if (datetime.datetime.now() - message.author.created_at) < faucet_settings.min_account_age:
				raise util.TipBotException("not_eligible")
			# check time since last faucet request, daily_wait set in faucet_settings.py
			if (datetime.datetime.now() - faucet_db.get_last_request(message.author)) < faucet_settings.daily_wait:
				raise util.TipBotException("not_eligible")
			# throw if first of last 4 faucet request timestamps within last 24 hours, daily_max set in faucet_settings.py
			if (datetime.datetime.now() - faucet_db.get_first_request(message.author)) < 60*60*24:
				raise util.TipBotException("not_eligible")

			# add new request
			faucet_db.add_new_request(message.author);

			# start faucet withdraw
			withdraw_address = find_address(message.content)
			botuser = db.get_user_by_id(faucet_settings.discord_bot_id, faucet_settings.discord_bot_name)
			if botuser is None:
				return
			source_id = botuser.user_id
			source_address = botuser.wallet_address
			balance = await wallet.get_balance(botuser)
			amount = balance['available']
			if amount == 0:
				await post_response(message, FAUCET_DRY);
			else:
				uid = str(uuid.uuid4())
				await wallet.make_transaction_to_address(botuser, faucet_settings.amount, withdraw_address, uid,verify_address = True)
				await post_response(message, WITHDRAW_SUCCESS_TEXT)
		except util.TipBotException as e:
			if e.error_type == "not_eligible":
				await post_response(message, NOT_ELIGIBLE)
			if e.error_type == "address_not_found":
				await post_response(message, WITHDRAW_ADDRESS_NOT_FOUND_TEXT)
			elif e.error_type == "invalid_address":
				await post_response(message, WITHDRAW_INVALID_ADDRESS_TEXT)
			elif e.error_type == "balance_error":
				await post_response(message, FAUCET_DRY)
			elif e.error_type == "error":
				await post_response(message, WITHDRAW_ERROR_TEXT)


async def faucetban(message):
	for member in message.mentions:
		if db.ban_user(member.id):
			await post_dm(message.author, BAN_SUCCESS, member.name)
		else:
			await post_dm(message.author, BAN_DUP, member.name)

async def faucetunban(message):
	for member in message.mentions:
		if db.unban_user(member.id):
			await post_dm(message.author, UNBAN_SUCCESS, member.name)
		else:
			await post_dm(message.author, UNBAN_DUP, member.name)


### Utility Functions
def get_qr_url(text):
	return 'https://chart.googleapis.com/chart?cht=qr&chl=%s&chs=180x180&choe=UTF-8&chld=L|2' % text

def find_address(input_text):
	address = input_text.split(' ')
	if len(address) == 1:
		raise util.TipBotException("address_not_found")
	elif address[1] is None:
		raise util.TipBotException("address_not_found")
	return address[1]

def find_amount(input_text):
	regex = r'(?:^|\s)(\d*\.?\d+)(?=$|\s)'
	matches = re.findall(regex, input_text, re.IGNORECASE)
	if len(matches) == 1:
		return float(matches[0].strip())
	else:
		raise util.TipBotException("amount_not_found")

### Re-Used Discord Functions
async def post_response(message, template, *args, incl_mention=True, mention_id=None):
	if mention_id is None:
		mention_id = message.author.id
	response = template % tuple(args)
	if not message.channel.is_private and incl_mention:
		response = "<@" + mention_id + "> \n" + response
	logger.info("sending response: '%s' to message: %s", response, message.content)
	asyncio.sleep(0.05) # Slight delay to avoid discord bot responding above commands
	return await client.send_message(message.channel, response)


async def post_dm(member, template, *args):
	response = template % tuple(args)
	logger.info("sending dm: '%s' to user: %s", response, member.id)
	try:
		asyncio.sleep(0.05)
		return await client.send_message(member, response)
	except:
		return None

async def post_edit(message, template, *args):
	response = template % tuple(args)
	return await client.edit_message(message, response)

async def remove_message(message):
	client_member = message.server.get_member(client.user.id)
	if client_member.permissions_in(message.channel).manage_messages:
		await client.delete_message(message)

async def add_x_reaction(message):
	await client.add_reaction(message, '\U0000274C') # X
	return

async def react_to_message(message, amount):
	if amount > 0:
		await client.add_reaction(message, '\:tip:425878628119871488') # TIP mark
		await client.add_reaction(message, '\:tick:425880814266351626') # check mark


# Start the bot
client.run(settings.discord_bot_token)
