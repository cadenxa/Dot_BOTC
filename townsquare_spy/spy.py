import json
import json.decoder
import secrets
import websockets

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

# Used to store the state of a session.

@dataclass
class Player:
    id: str = ''
    name: str = ''
    pronouns: str = ''
    is_dead: bool = False
    is_voteless: bool = False
    known_role: str = ''

@dataclass
class Session:
    log: Callable[[str], None] = lambda x: None
    players: list[Player] = field(default_factory=list)
    is_night: bool = False
    is_vote_history_allowed: bool = False
    nomination: Optional[list[int]] = None
    votes: set[int] = field(default_factory=set)
    is_vote_in_progress: bool = False
    locked_vote: int = 0
    marked_player: int = -1
    fabled: list[str] = field(default_factory=list)
    edition_name: str = ""

# Fancy (ANSI) formatting!
# See strip_ansi in spy_test.py for how to remove this.

def player_name(name):
    return f'\x1b[1;36m{name}\x1b[0m'

def player_pronouns(pronouns):
    return f'\x1b[0;36m{pronouns}\x1b[0m'

def player_full(player):
    desc = player_name(player.name)
    if player.pronouns:
        desc += f' ({player_pronouns(player.pronouns)})'
    if player.id:
        desc += f'\x1b[0;30m [{player.id}]\x1b[0m'
    if player.known_role:
        desc += f'\x1b[0;35m <{player.known_role}>\x1b[0m'
    if player.is_dead:
        desc += ' 💀'
        if not player.is_voteless:
            desc += '🗳️'
    return desc

def player_seat(name, id):
    desc = player_name(name)
    if id:
        desc += f'\x1b[0;30m [{id}]\x1b[0m'
    return desc

def night_or_day(is_night):
    if is_night:
        return '\x1b[0;34mnight\x1b[0m'
    return '\x1b[0;33mday\x1b[0m'

# This needs to handle the same messages that src/store/socket.js in bra1n/townsquare does in the "spectator" state.
# A little decorator is used to register which functions handle which messages.

message_handlers = {}

def townsquare_handler(name):
    def _decorator(func):
        message_handlers[name] = func
        return func
    return _decorator

@townsquare_handler('bye')
@townsquare_handler('claim')
@townsquare_handler('getGamestate')
@townsquare_handler('ping')
@townsquare_handler('votingSpeed')
@townsquare_handler('isVoteWatchingAllowed')  # clocktower.live extension
@townsquare_handler('allowSelfNaming')        # clocktower.live extension
def ignore_message(*args):
    """
    Ignore all arguments for the received message.
    """
    pass

@townsquare_handler('edition')
def set_edition(session, edition_info):
    """
    Changes the script.

    (object):
        edition (object):
            id (str): One of the known editions ("tb", "bmr", "snv", "luf") or "custom"
            name (str, optional): Name of the script (if custom)
            author (str, optional): Author of the script (if custom)
        roles (array):
            id or 0 (str): Character identifier
            ... remaining keys as numbers in the order they appear in src/store/index.js:
            ... id, name, image, ability, edition, etc
    """
    edition_name = edition_info['edition'].get('name', edition_info['edition']['id'].upper())
    session.log(f'The script was changed to {edition_name}.')
    session.edition_name = edition_name
    if edition_info.get('roles'):
        session.log('It contains: ' + ', '.join([r.get('id') or r.get('0') for r in edition_info['roles']]))

@townsquare_handler('gs')
def receive_game_state(session, state_info):
    """
    Receives a full or partial ("lightweight") update of the game state.
    Currently a lightweight one is never requested by this client; it excludes
    information aside from the current players' states.

    (object):
        gamestate (array):
            name (str): Player's name
            id (str): Player's ID
            pronouns (str): Player's preferred pronouns
            isDead (bool): True if the player is dead
            isVoteless (bool): True if the player has spent their dead vote
        isNight (bool): True if the game is in the night phase
        isVoteHistoryAllowed (bool): True if players may view vote history
        nomination (null or [int, int]): If a nomination is going on, which player nominated which
        votes ([bool], optional): By player index, whether the player's hand is up (if a nomination is going on)
        isVoteInProgress (bool): Whether a vote is currently running
        lockedVote (int): During a vote, how many votes are locked
        markedPlayer (int): Which player index, if any, is marked (-1 if none)
        fabled (array):
            id (str): Fabled which is in play
            ... other properties (if custom)
    """
    previous_player_names = [p.name for p in session.players]
    previous_fabled = session.fabled

    if isinstance(state_info.get('gamestate'), list):
        session.players = [
            Player(
                id=p.get("id", ""),
                name=p.get("name", ""),
                pronouns=p.get("pronouns", ""),
                is_dead=p.get("isDead", False),
                is_voteless=p.get("isVoteless", False),
                known_role=p.get("roleId", ""),
            )
            for p in state_info['gamestate']
        ]
    is_lightweight = state_info.get('isLightweight', False)
    if not is_lightweight:
        session.is_night = state_info.get('isNight', False)
        session.is_vote_history_allowed = state_info.get('isVoteHistoryAllowed', False)
        session.nomination = state_info.get('nomination', None)
        session.votes = {i for i, v in enumerate(state_info.get('votes', [])) if v}
        session.is_vote_in_progress = state_info.get('isVoteInProgress', False)
        session.locked_vote = state_info.get('lockedVote', 0)
        session.marked_player = state_info.get('markedPlayer', -1)
        session.fabled = [f['id'] for f in state_info.get('fabled', [])]

    if not is_lightweight:
        session.log('Players:')
        for p in session.players:
            session.log(f'* {player_full(p)}')
    else:
        new_player_names = [p.name for p in session.players]
        for p in new_player_names:
            if p not in previous_player_names:
                session.log(f'A seat was added for {player_name(p)}.')
        for p in previous_player_names:
            if p not in new_player_names:
                session.log(f'{player_name(p)} was removed.')

    if not is_lightweight:
        session.log('Fabled: ' + ', '.join(f'\x1b[0;33m{f}\x1b[0m' for f in session.fabled))
    else:
        for f in previous_fabled:
            if f not in session.fabled:
                session.log(f'Fabled \x1b[0;33m{f}\x1b[0m was removed.')
        for f in session.fabled:
            if f not in previous_fabled:
                session.log(f'Fabled \x1b[0;33m{f}\x1b[0m was added.')

    if not is_lightweight:
        session.log(f'It is currently {night_or_day(session.is_night)}.')

    if not is_lightweight and session.marked_player >= 0:
        session.log(f'{player_name(session.players[session.marked_player].name)} is marked for execution.')

    if not is_lightweight and session.nomination:
        nominator, nominee = session.nomination
        session.log(f'{player_name(session.players[nominator].name)} is in the process of nominating {player_name(session.players[nominee].name)}.')

@townsquare_handler('isNight')
def change_night_phase(session, new_value = None):
    """
    Changes from day to night, or night to day.

    new_value (bool): True for night, false for day
                    Historically, this being absent means to toggle night.
    """
    if new_value is None:
        new_value = not session.is_night
    session.is_night = new_value
    session.log(f'It is now {night_or_day(session.is_night)}.')


@townsquare_handler('isVoteHistoryAllowed')
def change_vote_history(session, new_value):
    """
    Changes whether players may view the vote history.

    new_value (bool): True for vote history enabled
    """
    session.is_vote_history_allowed = new_value
    session.log('Vote history was turned ' + ('on' if session.is_vote_history_allowed else 'off'))
    
@townsquare_handler('clearVoteHistory')
def clear_vote_history(session, *args):
    """
    Clears vote history.
    """
    session.log('Vote history was cleared.')

@townsquare_handler('player')
def update_player(session, update):
    """
    Updates a player, such as whether they are seated, pronouns, and life status.
    These are pushed by the host, so though other spectators observe player
    requests to change these, the host's updates are sufficient.

    (object):
        index (int): player to update, by index
        property (str): property of the player which has changed
        value (any): new value of the property
    """
    index, property, value = update['index'], update['property'], update['value']
    player = session.players[index]
    if property == 'id':
        if not value:
            session.log(f'{player_seat(player.name, player.id)} left their seat.')
        else:
            session.log(f'{player_seat(player.name, value)} claimed their seat.')
        player.id = value
    elif property == 'name':
        session.log(f'{player_name(player.name)} was renamed {player_name(value)}.')
        player.name = value
    elif property == 'pronouns':
        player.pronouns = value
        if value:
            session.log(f'{player_name(player.name)} changed their pronouns to {player_pronouns(player.pronouns)}.')
        else:
            session.log(f'{player_name(player.name)} cleared their pronouns.')
    elif property == 'isDead':
        player.is_dead = value
        if value:
            session.log(f'{player_name(player.name)} died.')
        else:
            session.log(f'{player_name(player.name)} came back to life.')
    elif property == 'isVoteless':
        player.is_voteless = value
        if value:
            session.log(f'{player_name(player.name)} spent their dead vote.')
        elif player.is_dead:
            session.log(f'{player_name(player.name)}\'s dead vote was restored.')
    elif property == 'role':
        if value:
            player.known_role = value
            session.log(f'{player_name(player.name)} became a \x1b[0;35m{value}\x1b[0m (traveler).')
        else:
            player.known_role = ''
            session.log(f'{player_name(player.name)} became a resident.')

@townsquare_handler('pronouns')
def change_pronouns(session, pronoun_info):
    index, pronouns = pronoun_info
    player = session.players[index]
    player.pronouns = pronouns
    if pronouns:
        session.log(f'{player_name(player.name)} changed their pronouns to {player_pronouns(player.pronouns)}.')
    else:
        session.log(f'{player_name(player.name)} cleared their pronouns.')

# clocktower.live extension
@townsquare_handler('name')
def change_name(session, name_info):
    index, new_name = name_info
    player = session.players[index]
    old_name, player.name = player.name, new_name
    session.log(f'{player_name(old_name)} changed their name to {player_name(new_name)}.')

@townsquare_handler('nomination')
def nominate(session, nom = None):
    """
    Start or end a nomination.

    (array or null): If an array, it is a [nominator, nominee] pair.
    """
    if nom is None:
        if not session.nomination:
            pass
        elif session.locked_vote <= len(session.players):
            session.log(f'Vote was cancelled.')
        else:
            session.log(f'The following players voted: ' +
                  ', '.join(player_name(session.players[p].name) for p in sorted(session.votes)))
    else:
        players = session.players
        session.log(f'{player_name(players[nom[0]].name)} nominated {player_name(players[nom[1]].name)}.')
        session.votes = set()
        session.is_vote_in_progress = False
        session.locked_vote = 0
    session.nomination = nom

@townsquare_handler('swap')
def swap_players(session, indices):
    """
    Swap the seats of two players.

    (array): The indices of the two players which were swapped.
    """
    players = session.players
    i, j = indices
    session.log(f'{player_name(players[i].name)} and {player_name(players[j].name)} swapped seats.')
    players[i], players[j] = players[j], players[i]

@townsquare_handler('move')
def move_player(session, indices):
    """
    Move the seat of one player.

    (array): The index of the moved player and the new index.
    """
    players = session.players
    i, j = indices
    session.log(f'{player_name(players[i].name)} moved to seat {j}.')
    player = players[i]
    del players[i]
    players.insert(j, player)

@townsquare_handler('remove')
def remove_player(session, index):
    """
    Remove a seat.

    (int): The index of the removed player.
    """
    players = session.players
    session.log(f'{player_name(players[index].name)} was removed.')
    del players[index]

@townsquare_handler('marked')
def mark_player(session, index):
    """
    Mark/unmark a player for execution.

    (int): Index of the player who is marked (or -1 to clear)
    """
    if index < 0:
        session.log(f'The execution mark was cleared.')
    else:
        session.log(f'{player_name(session.players[index].name)} was marked for execution.')
    session.marked_player = index

@townsquare_handler('isVoteInProgress')
def start_end_vote(session, status):
    """
    Start/end a vote.

    (bool): Whether a vote is in progress.
    """
    session.is_vote_in_progress = status

@townsquare_handler('vote')
def update_vote(session, info):
    """
    Update a player's vote.

    (array):
        0 (int): Player index
        1 (any): null or false for no vote, true for vote
        2 (bool): Whether this is the ST overriding a player vote
    """
    if not session.nomination:
        return
    index, vote, from_st = info
    index_locked = (index - 1 - session.nomination[1]) % len(session.players)
    if from_st or index_locked >= session.locked_vote - 1:
        if vote:
            session.votes.add(index)
        else:
            session.votes.discard(index)

@townsquare_handler('lock')
def lock_vote(session, info):
    """
    Lock in a player's vote (as observed by the host).

    (array):
        0 (int): Player index, where the nominated player is 0 and the first player to vote is 1
        1 (any): null or 0 for no vote, 1 for vote
    """
    relative, vote = info
    session.locked_vote = relative
    if relative <= 1:
        return
    index = (session.nomination[1] + relative - 1) % len(session.players)
    if vote:
        session.votes.add(index)
    else:
        session.votes.discard(index)

@townsquare_handler('fabled')
def update_fabled(session, fabled):
    """
    Adds or removed fabled characters from play.

    (array):
        id (str): ID of fabled character
        ... other properties (if custom)
    """
    previous_fabled = session.fabled
    session.fabled = [f['id'] for f in fabled]
    for f in previous_fabled:
        if f not in session.fabled:
            session.log(f'Fabled \x1b[0;33m{f}\x1b[0m was removed.')
    for f in session.fabled:
        if f not in previous_fabled:
            session.log(f'Fabled \x1b[0;33m{f}\x1b[0m was added.')

def receive(session, m):
    if not m or not isinstance(m, list) or not isinstance(m[0], str):
        raise ValueError('malformed message')

    # Message handlers are registered above.
    handler = message_handlers.get(m[0])
    if not handler:
        raise ValueError('unrecognized message type ' + repr(m[0]))

    handler(session, *m[1:])

def random_player_id():
    return f'spy_{secrets.token_hex(4)}'

# Known servers:
# https://clocktower.online -> wss://live.clocktower.online:8080/{session}/{player_id}
# https://clocktower.live -> wss://clocktower.live:8001/{session}/{player_id}
def interpret_url(game_url, player_id):
    u = urlparse(game_url)
    session_name = u.fragment
    socket_url = None
    if u.hostname == 'clocktower.online':
        socket_url = f'wss://live.clocktower.online:8080/{session_name}/{player_id}'
    elif u.hostname == 'clocktower.live':
        socket_url = f'wss://clocktower.live:8001/{session_name}/{player_id}'
    if not session_name or not socket_url:
        raise ValueError('unknown game URL', game_url)
    return (socket_url, f'{u.scheme}://{u.netloc}')

async def connect_to_session(socket_url, origin, player_id):
    async with websockets.connect(socket_url, origin=origin) as ws:
        await ws.send(json.dumps(["direct", {"host": ["getGamestate", player_id]}]))
        while True:
            try:
                m = json.loads(await ws.recv())
            except json.decoder.JSONDecodeError:
                continue
            yield m
