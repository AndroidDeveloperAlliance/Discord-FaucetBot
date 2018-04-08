# Discord
discord_bot_name = 'B Faucet Bot';
discord_bot_id = '';
discord_bot_token = '';
# Nano node wallet ID
wallet = '';
# Exempt users list (these user IDs will not be able to receive tips
exempt_users = [ discord_bot_id, '395828286548344834', '405250059240996864', '418425979942207499' ]
# Restricted roles for certain commands
admin_roles = ['Moderators', 'Core', 'Community Managers','Admin', 'DJ']
# min account age (30 days)
min_account_age = 60*60*24*30
# Wait between faucet requests
daily_wait = 60*60
# amount
amount = 30
# unit
unit='BANANO'
# command prefix
command_prefix='$'
# Status
playing_status='send me ' + command_prefix + 'help in private'
# Maximum faucet request - IF YOU CHANGE THIS, YOU HAVE TO UPDATE A BUNCH OF OTHER STUFF IN THE FAUCET.DB AND FAUCET.BOT!!!!
daily_max = 4
