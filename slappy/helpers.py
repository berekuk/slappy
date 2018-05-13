from typing import Dict

class Channel:
    def __init__(self, sc, data: Dict):
        self.data = data

class User:
    def __init__(self, sc, data: Dict):
        self.data = data

    @property
    def name(self) -> str:
        return self.data['name']

def get_channel(sc, channel_id: str) -> Channel:
    response = sc.api_call('channels.info', channel=channel_id)
    if not response['ok']:
        raise Exception(response['error'])

    return Channel(sc, response['channel'])

def get_user(sc, user_id: str) -> User:
    response = sc.api_call('users.info', user=user_id)
    if not response['ok']:
        raise Exception(response['error'])

    return User(response['user'])
