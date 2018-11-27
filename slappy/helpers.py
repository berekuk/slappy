import logging
logger = logging.getLogger(__name__)

from typing import Dict

class Channel:
    def __init__(self, sc, data: Dict):
        self.data = data

    @property
    def channel_id(self):
        return self.data['id']

    @property
    def name(self) -> str:
        return self.data['name']


class User:
    def __init__(self, sc, data: Dict):
        self.data = data

    @property
    def name(self) -> str:
        return self.data['name']


def get_channel(sc, channel_id: str) -> Channel:
    response = sc.api_call('channels.info', channel=channel_id)
    if not response['ok']:
        logger.error(response)
        raise Exception(response['error'])

    return Channel(sc, response['channel'])


def get_user(sc, user_id: str) -> User:
    response = sc.api_call('users.info', user=user_id)
    if not response['ok']:
        logger.error(response)
        raise Exception(response['error'])

    return User(sc, response['user'])


def get_channel_by_name(sc, channel_name: str) -> Channel:
    response = sc.api_call('channels.list')
    if not response['ok']:
        logger.error(response)
        raise Exception(response['error'])

    channel_info = next(
        (c for c in response['channels'] if c['name'] == channel_name),
        None
    )
    if not channel_info:
        raise Exception(f"Channel {channel_name} not found")

    return Channel(sc, channel_info)
