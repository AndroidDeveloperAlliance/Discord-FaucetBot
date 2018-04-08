import datetime
import util
import faucet_settings
from peewee import *
from playhouse.sqliteq import SqliteQueueDatabase


db = SqliteQueueDatabase('bananodiscord.db')

logger = util.get_logger("db")

### User Stuff
def add_new_request(user):
	try:
		fuser = FaucetUser.get(user_id == user.user_id)
		fuser.last_request_1=fuser.last_request_2
		fuser.last_request_2=fuser.last_request_3
		fuser.last_request_3=fuser.last_request_4
		fuser.last_request_4=datetime.datetime.now()
		fuser.request_count = fuser.request_count + 1
		fuser.save();
	except FaucetUser.DoesNotExist:
		create_fuser(user.user_id, user.user_name);
		add_new_request(user);
		return None

def get_first_request(user):
	try:
		fuser = FaucetUser.get(user_id == user.user_id)
		return fuser.last_request_1
	except FaucetUser.DoesNotExist:
		create_fuser(user.user_id, user.user_name);
		get_first_request(user);
		return None

def get_last_request(user):
	try:
		fuser = FaucetUser.get(user_id == user.user_id)
		return fuser.last_request_4
	except FaucetUser.DoesNotExist:
		create_fuser(user.user_id, user.user_name);
		get_last_request(user);
		return None

def create_fuser(user_id, user_name):
	fuser = FaucetUser(user_id=user_id,
		    user_name=user_name,
		    last_request_1=datetime.datetime.fromtimestamp(1284286794),
		    last_request_2=datetime.datetime.fromtimestamp(1284286794),
		    last_request_3=datetime.datetime.fromtimestamp(1284286794),
		    last_request_4=datetime.datetime.fromtimestamp(1284286794),
		    request_count=0,
		    created=datetime.datetime.now(),
		    )
	fuser.save()
	return user

# User table
class FaucetUser(Model):
	user_id = CharField(unique=True)
	user_name = CharField()
	last_request_1 = DateTimeField()
	last_request_2 = DateTimeField()
	last_request_3 = DateTimeField()
	last_request_4 = DateTimeField()
	request_count = IntegerField()
	created = DateTimeField()

	class Meta:
		database = db

def create_db():
	db.connect()
	db.create_tables([FaucetUser], safe=True)
	logger.debug("DB Connected")

create_db()
