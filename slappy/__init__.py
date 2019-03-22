import logging
logger = logging.getLogger(__name__)

import re
import json
import traceback

from flask import request, jsonify

from apscheduler.schedulers.background import BackgroundScheduler

from slackeventsapi import SlackEventAdapter
from slackclient import SlackClient

from typing import List, Dict

import slappy.helpers

class ErrorResponse(Exception):
    pass

class Message:
    def __init__(self, body, sc):
        self.body = body
        self.sc = sc

    def is_text_message(self):
        if self.body.get('type', None) != 'message':
            return False

        if 'text' not in self.body:
            return False

        return True

    def reply(self, text, **kwargs):
        args = dict(**kwargs)
        args['text'] = text
        args['channel'] = self.channel_id
        if 'thread_ts' in self.body:
            args['thread_ts'] = self.body['thread_ts']

        result = self.sc.api_call('chat.postMessage', **args)
        if not result['ok']:
            raise Exception(str(result))

    def react(self, emoji):
        result = self.sc.api_call(
            'reactions.add',
            name=emoji,
            channel=self.channel_id,
            timestamp=self.body['ts'],
        )
        if not result['ok']:
            raise Exception(result['error'])

    @property
    def channel_id(self) -> str:
        return self.body['channel']

    @property
    def channel(self) -> slappy.helpers.Channel:
        channel_type = self.body['channel_type']
        if channel_type == 'channel':
            return slappy.helpers.get_channel(self.sc, self.channel_id)
        else:
            return # groups or other channel types not implemented yet

    @property
    def user_id(self) -> str:
        return self.body['user']

    @property
    def user(self) -> slappy.helpers.User:
        return slappy.helpers.get_user(self.sc, self.user_id)

    def typing(self):
        return # not working anymore - can only be used on RTM API, but we use Events API now

        found_channel = self.sc.server.channels.find(self.channel_id)
        channel_id = found_channel.id if found_channel else self.channel_id

        self.sc.api_call({
            'id': 1,
            'type': 'typing',
            'channel': channel_id,
        })


class Listener:
    def __init__(self, regex, f, mention_only=False):
        self.regex = regex
        self.f = f
        self.mention_only = mention_only

    def match(self, text):
        return re.match(self.regex, text, flags=re.IGNORECASE)

    def process(self, msg, match):
        args = (msg,) + match.groups() # type: ignore
        result = self.f(*args)

        if type(result) == str:
            msg.reply(text=result)
        elif type(result) == dict:
            msg.reply(**result)
        elif result:
            raise Exception('Bad listener result: {}'.format(result))


class Dispatcher:
    def __init__(self, bot_id: str, alt_names: List[str] = []):
        self.listeners: List[Dict] = []
        self.actions: List[Dict] = []
        self.commands: List[Dict] = {}
        self.alt_names = alt_names
        self.bot_id = bot_id

    def register_listener(self, listener):
        self.listeners.append(listener)

    def register_action(self, regex, f):
        self.actions.append({
            'regex': regex,
            'f': f,
        })

    def register_command(self, name, f):
        if name in self.commands:
            raise Exception('Duplicate command {}'.format(name))
        self.commands[name] = {
            'f': f
        }

    def process_action(self, payload):
        for action in self.actions:
            match = re.match(action['regex'], payload['callback_id'])
            if not match:
                continue

            args = (payload,) + match.groups() # type: ignore # (for some reason typing.py defines groups() as Sequence, not Tuple)
            return action['f'](*args) # any action which listens for a route should process it (note that it's different with listeners)

        raise Exception('unknown action')

    def parse_mention(self, text: str) -> (bool, str):
        mention_match = re.match(r'<@(\w+)>,?\s*(.*)', text)
        if mention_match:
            (user_id, short_text) = mention_match.groups()
            if user_id == self.bot_id:
                return (True, short_text)

        if self.alt_names:
            alt_names_regex = '|'.join([re.escape(name) for name in self.alt_names])
            regex = '(?:' + alt_names_regex + ')' + r',\s*(.*)'
            mention_match = re.match(regex, text, flags=re.IGNORECASE)
            if mention_match:
                text = mention_match.group(1)
                return (True, text)

        return (False, text)

    def process_message(self, msg):
        if not msg.is_text_message():
            return

        text = msg.body['text']

        (mentioned, text) = self.parse_mention(text)

        direct = msg.body['channel_type'] == 'app_home'

        for listener in self.listeners:
            if listener.mention_only and (not mentioned and not direct):
                continue

            match = listener.match(text)
            if not match:
                continue

            logger.debug(f"{msg.body['text']} matches {str(listener)}")
            listener.process(msg, match)

            return # one listener is enough

        logger.debug(f"{msg.body['text']} doesn't match anything")
        if mentioned or direct:
            msg.reply('Не понимаю.')

    def process_command(self, payload):
        command = payload['command']
        if command not in self.commands:
            raise Exception('Command {} not found'.format(command))

        return self.commands[command]['f'](payload)

class Bot:
    def __init__(self, workplace_token, signing_secret, timezone=None, alt_names=[]):
        scheduler_options = {}
        if timezone:
            scheduler_options['timezone'] = timezone
        self.scheduler = BackgroundScheduler(**scheduler_options)

        self.sc = SlackClient(workplace_token)
        self.slack_events_adapter = SlackEventAdapter(
            signing_secret,
            endpoint="/slack/events"
        )

        self.alt_names = alt_names

        self.bot_id = self.get_bot_id()
        self.dispatcher = Dispatcher(self.bot_id, self.alt_names)

    def get_bot_id(self):
        response = self.sc.api_call('users.profile.get')
        if not response['ok']:
            raise Exception(response['error'])

        bot_id = response['profile']['bot_id']
        response = self.sc.api_call('bots.info', bot=bot_id)
        if not response['ok']:
            raise Exception(response['error'])

        bot_user_id = response['bot']['user_id']
        return bot_user_id

    @property
    def flask_app(self):
        return self.slack_events_adapter.server

    ### Decorators ###
    def listen_to(self, regex):
        def wrap(f):
            self.dispatcher.register_listener(Listener(regex, f))
            return f
        return wrap

    def respond_to(self, regex):
        def wrap(f):
            self.dispatcher.register_listener(Listener(regex, f, mention_only=True))
            return f
        return wrap

    def schedule(self, trigger, **kwargs):
        def wrap(f):
            def job(*args, **kwargs):
                try:
                    f(*args, **kwargs)
                    self.cleanup_on_anything()
                except:
                    self.cleanup_on_exception()
                    raise

            self.scheduler.add_job(job, trigger, **kwargs)
        return wrap

    def action(self, regex):
        def wrap(f):
            self.dispatcher.register_action(regex, f)
        return wrap

    def command(self, name):
        def wrap(f):
            self.dispatcher.register_command(name, f)
            return f
        return wrap

    ### Public helper methods ###
    def send_message(self, **kwargs):
        result = self.sc.api_call('chat.postMessage', **kwargs)
        if not result['ok']:
            raise Exception(str(result))


    ### Run and internal methods ###
    def process_message(self, msg):
        if 'bot_id' in msg:
            return

        msg = Message(msg, self.sc)
        try:
            self.dispatcher.process_message(msg)
            self.cleanup_on_anything()
        except Exception as e:
            traceback.print_exc()
            self.cleanup_on_exception()
            msg.reply('Что-то пошло не так: ```{}```'.format(str(e)))

    def run(self, host='127.0.0.1', port=None):
        self.scheduler.start()

        @self.flask_app.route('/slack/action', methods=['POST'])
        def act():
            payload = json.loads(request.form['payload'])

            try:
                result = self.dispatcher.process_action(payload)
                self.cleanup_on_anything()
            except:
                self.cleanup_on_exception()
                raise

            if not result:
                return ''

            return jsonify(result)

        @self.flask_app.route('/slack/command', methods=['POST'])
        def command():
            payload = request.form

            try:
                result = self.dispatcher.process_command(payload)
                self.cleanup_on_anything()
            except Exception as e:
                self.cleanup_on_exception()
                return 'Что-то пошло не так: ```{}```'.format(str(e))

            if type(result) == str:
                return result
            else:
                return jsonify(result)

        @self.slack_events_adapter.on("message")
        def on_event(event):
            if request.headers.get('X-Slack-Retry-Reason') == 'http_timeout':
                logger.warning('Got a retry request because of timeout')
                return

            self.process_message(event['event'])

        self.slack_events_adapter.start(host=host, port=port)

    # override this method to remove sqlalchemy sessions etc. after exceptions
    def cleanup_on_exception(self):
        pass

    # override this method to remove sqlalchemy sessions etc. after a normal action
    # (I'm having issues even though I'm using Flask-SQLAlchemy for some reason)
    def cleanup_on_anything(self):
        pass
