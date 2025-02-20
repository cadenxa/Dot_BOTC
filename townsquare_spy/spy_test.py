"""
Unit tests for the game logic.

This is isolated from the websocket client by using pre-canned messages.
"""

import pytest
import re

from spy import *

def strip_ansi(s):
    return re.sub(r'\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]', '', s)

def simulated_session():
    output = []
    session = Session()
    session.log = lambda message: output.append(strip_ansi(message))
    return (session, output)

def any_line_matches(output, pattern):
    return any(re.search(pattern, strip_ansi(l)) for l in output)

def basic_gs(player_count=8):
    player_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima", "Mike", "November", "Oscar", "Papa", "Quebec", "Romeo", "Sierra", "Tango"][:player_count]
    return dict(
        gamestate=[
            dict(name=name,
                 id=f'PlayerID{idx:02}',
                 isDead=False,
                 isVoteless=False,
                 pronouns="")
            for idx, name in enumerate(player_names)
        ],
        isNight=False,
        isVoteHistoryAllowed=True,
        nomination=False,
        votingSpeed=1000,
        lockedVote=0,
        isVoteInProgress=False,
        markedPlayer=-1,
        fabled=[]
    )

def test_shows_edition():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    assert any_line_matches(output, r'script.*TB'), "expected to see script change"

def test_shows_edition_change():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["edition", {"edition": {"id": "bmr"}}])
    assert any_line_matches(output, r'script.*BMR'), "expected to see script change"

def test_shows_custom_edition():
    session, output = simulated_session()
    custom_roles = [
        dict(id=id)
        for id in ["clockmaker", "investigator", "empath", "chambermaid", "artist", "sage", "drunk", "klutz", "scarlet_woman", "baron", "imp"]
    ]
    custom_edition = dict(id="custom",
                          name="No Greater Joy",
                          author="Steven Medway")
    receive(session, ["edition", {"edition": custom_edition, "roles": custom_roles}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    assert any_line_matches(output, r'script.*No Greater Joy'), "expected to see script change"
    assert any_line_matches(output, r'chambermaid'), "expected to see character list"

def test_shows_homebrew_edition():
    session, output = simulated_session()
    custom_roles = [
        dict(id="villager",
             name="Villager",
             edition="example",
             team="townsfolk",
             ability="You have no ability."),
        dict(id="werewolf",
             name="Werewolf",
             edition="example",
             team="demon",
             ability="Each night*, choose a player: they die.",
             otherNight=10,
             otherNightReminder="The Werewolf chooses a player. :reminder: They die.",
             reminders=["Dead"])
    ]
    custom_edition = dict(id="custom", name="Werewolf", author="")
    receive(session, ["edition", {"edition": custom_edition, "roles": custom_roles}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    assert any_line_matches(output, r'script.*Werewolf'), "expected to see script change"
    assert any_line_matches(output, r'villager'), "expected to see character list"

def test_shows_player_names_and_ids():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    assert session.players[5].id == 'PlayerID05'
    assert session.players[5].name == 'Foxtrot'
    assert any_line_matches(output, r'Foxtrot')
    assert any_line_matches(output, r'PlayerID05')

def test_shows_player_starting_life():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["gamestate"][0]["isDead"] = True
    gs["gamestate"][1]["isDead"] = True
    gs["gamestate"][1]["isVoteless"] = True
    receive(session, ["gs", gs])
    assert session.players[0].is_dead
    assert not session.players[0].is_voteless
    assert any_line_matches(output, "Alpha.*💀")
    assert any_line_matches(output, "Alpha.*🗳")
    assert session.players[1].is_dead
    assert session.players[1].is_voteless
    assert any_line_matches(output, "Bravo.*💀")
    assert not any_line_matches(output, "Bravo.*🗳")
    assert not session.players[2].is_dead
    assert not session.players[2].is_voteless
    assert not any_line_matches(output, "Charlie.*💀")
    assert not any_line_matches(output, "Charlie.*🗳")

def test_shows_starting_traveler():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["gamestate"][3]["roleId"] = "scapegoat"
    receive(session, ["gs", gs])
    assert session.players[3].name == 'Delta'
    assert session.players[3].known_role == 'scapegoat'
    assert any_line_matches(output, r'Delta.*scapegoat')

def test_shows_starting_fabled():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["fabled"] = [{"id": "hellslibrarian"}]
    receive(session, ["gs", gs])
    assert session.fabled == ["hellslibrarian"]
    assert any_line_matches(output, r'hellslibrarian')

def test_shows_starting_day():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["isNight"] = False
    receive(session, ["gs", gs])
    assert session.is_night == False
    assert any_line_matches(output, r'It is currently day.')

def test_shows_starting_night():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["isNight"] = True
    receive(session, ["gs", gs])
    assert session.is_night == True
    assert any_line_matches(output, r'It is currently night.')

def test_shows_starting_execution_mark():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["markedPlayer"] = 4
    receive(session, ["gs", gs])
    assert any_line_matches(output, r'Echo.*marked')

# In practice, adding a player causes a lightweight update.
def test_add_player_lightweight():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=1)
    player = gs["gamestate"].pop()
    player["id"] = ""
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["gs", {"gamestate": [player], "isLightweight": True}])
    assert session.players[0].id == ""
    assert session.players[0].name == "Alpha"
    assert any_line_matches(output, r'seat.*added.*Alpha')

# In practice, removing a player causes a remove message.
def test_remove_player_lightweight():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=1)
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["remove", 0])
    assert len(session.players) == 0
    assert any_line_matches(output, r'Alpha.*removed')

def test_add_fabled():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["fabled", [{"id": "buddhist"}]])
    assert session.fabled == ["buddhist"]
    assert any_line_matches(output, r'buddhist.*added')

def test_remove_fabled():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["fabled"] = [{"id": "angel"}]
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["fabled", []])
    assert session.fabled == []
    assert any_line_matches(output, r'angel.*removed')

def test_day_night():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["isNight", True])
    assert session.is_night
    assert any_line_matches(output, r'It is now night')
    output.clear()
    receive(session, ["isNight", False])
    assert not session.is_night
    assert any_line_matches(output, r'It is now day')

def test_vote_history():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["isVoteHistoryAllowed", False])
    assert not session.is_vote_history_allowed
    assert any_line_matches(output, r'Vote history.*off')
    output.clear()
    receive(session, ["isVoteHistoryAllowed", True])
    assert session.is_vote_history_allowed
    assert any_line_matches(output, r'Vote history.*on')
    output.clear()
    receive(session, ["clearVoteHistory", None])
    assert any_line_matches(output, r'Vote history.*cleared')

def test_rename_player():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["player", dict(index=2, property="name", value="Charles")])
    receive(session, ["pronouns", [2, "he/him"]])
    receive(session, ["allowSelfNaming", True])
    receive(session, ["name", [2, "Charlie"]])
    assert session.players[2].name == "Charlie"
    assert session.players[2].pronouns == "he/him"
    assert any_line_matches(output, r'Charlie.*renamed.*Charles')
    assert any_line_matches(output, r'Charles.*he/him')
    assert any_line_matches(output, r'Charles.*Charlie')

def test_death_resurrection():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["player", dict(index=1, property="isDead", value=True)])
    assert session.players[1].is_dead
    assert any_line_matches(output, r'Bravo died')
    output.clear()
    receive(session, ["player", dict(index=1, property="isDead", value=False)])
    assert not session.players[1].is_dead
    assert any_line_matches(output, r'Bravo came back to life')

def test_dead_vote():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    receive(session, ["player", dict(index=1, property="isDead", value=True)])
    output.clear()
    receive(session, ["player", dict(index=1, property="isVoteless", value=True)])
    assert session.players[1].is_voteless
    assert any_line_matches(output, r'Bravo spent.*dead vote')
    output.clear()
    receive(session, ["player", dict(index=1, property="isVoteless", value=False)])
    receive(session, ["player", dict(index=1, property="isDead", value=False)])
    assert not session.players[1].is_voteless
    assert any_line_matches(output, r'Bravo.*dead vote.*restored')

def test_toggle_traveler():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["player", dict(index=6, property="role", value="beggar")])
    assert session.players[6].known_role == "beggar"
    assert any_line_matches(output, "became.*beggar")
    output.clear()
    receive(session, ["player", dict(index=6, property="role", value="")])
    assert not session.players[6].known_role
    assert any_line_matches(output, "became.*resident")

def test_mark_for_execution():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["marked", 6])
    assert session.marked_player == 6
    assert any_line_matches(output, "Golf.*marked")
    output.clear()
    receive(session, ["marked", -1])
    assert session.marked_player == -1
    assert any_line_matches(output, "mark.*cleared")

def test_nominate_and_cancel():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", [4, 5]])
    assert session.nomination == [4, 5]
    assert any_line_matches(output, "Echo nominated Foxtrot")
    output.clear()
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    assert not session.nomination
    assert any_line_matches(output, "cancelled")

def test_nominate_and_cancel_with_running_vote():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", [0, 0]])
    assert session.nomination == [0, 0]
    assert any_line_matches(output, "Alpha nominated Alpha")
    output.clear()
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, 1]])
    receive(session, ["lock", [3, None]])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    assert not session.nomination
    assert any_line_matches(output, "cancelled")

def test_complete_vote():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", [0, 0]])
    assert session.nomination == [0, 0]
    assert any_line_matches(output, "Alpha nominated Alpha")
    output.clear()
    receive(session, ["vote", [1, 1, False]])
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, 1]])
    receive(session, ["vote", [3, 1, False]])
    receive(session, ["lock", [3, None]])
    receive(session, ["vote", [3, 0, False]])
    receive(session, ["lock", [4, 0]])
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, None]])
    receive(session, ["lock", [7, None]])
    receive(session, ["lock", [8, None]])
    receive(session, ["lock", [9, None]])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    assert not session.nomination
    assert any_line_matches(output, "voted:.*Bravo")
    assert not any_line_matches(output, "voted:.*Charlie")
    assert not any_line_matches(output, "voted:.*Delta")
    assert not any_line_matches(output, "cancelled")

def test_two_votes_one_nom():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=5)
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", [0, 0]])
    assert session.nomination == [0, 0]
    assert any_line_matches(output, "Alpha nominated Alpha")
    output.clear()
    # First vote
    receive(session, ["vote", [1, 1, False]])
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, 1]])
    receive(session, ["vote", [3, 1, False]])
    receive(session, ["lock", [3, None]])
    receive(session, ["vote", [3, 0, False]])
    receive(session, ["lock", [4, 0]])
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, None]])
    receive(session, ["isVoteInProgress", False])
    # ST ran the vote again
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["vote", [1, 0, False]])
    receive(session, ["vote", [3, 1, False]])
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, 0]])
    receive(session, ["lock", [3, None]])
    receive(session, ["lock", [4, 1]])
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, None]])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    # Only the last vote counts
    assert not session.nomination
    assert not any_line_matches(output, "voted:.*Bravo")
    assert any_line_matches(output, "voted:.*Delta")

def test_join_during_nomination():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=5)
    gs["nomination"] = [1, 0]
    receive(session, ["gs", gs])
    assert session.nomination == [1, 0]
    assert any_line_matches(output, "Bravo.*nom.*Alpha")
    output.clear()
    receive(session, ["vote", [1, 1, False]])
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, 1]])
    receive(session, ["vote", [3, 1, False]])
    receive(session, ["lock", [3, None]])
    receive(session, ["vote", [3, 0, False]])
    receive(session, ["lock", [4, 0]])
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, None]])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    assert not session.nomination
    assert any_line_matches(output, "voted:.*Bravo")

def test_join_before_vote():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=5)
    gs["nomination"] = [0, 0]
    gs["isVoteInProgress"] = True
    gs["lockedVote"] = 0
    gs["votes"] = []
    receive(session, ["gs", gs])
    assert session.nomination == [0, 0]
    assert any_line_matches(output, "Alpha.*nom.*Alpha")
    output.clear()
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, None]])
    receive(session, ["lock", [3, None]])
    receive(session, ["lock", [4, None]])
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, None]])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    assert not session.nomination
    assert any_line_matches(output, r'voted:\s*$')

def test_join_during_vote():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=8)
    gs["nomination"] = [0, 0]
    gs["isVoteInProgress"] = True
    gs["lockedVote"] = 4
    gs["votes"] = [None, 0, None, 1]
    receive(session, ["gs", gs])
    assert session.nomination == [0, 0]
    assert any_line_matches(output, "Alpha.*nom.*Alpha")
    output.clear()
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, None]])
    receive(session, ["vote", [5, 1, False]])
    receive(session, ["lock", [7, 1]])
    receive(session, ["lock", [8, None]])
    receive(session, ["lock", [9, None]])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", None])
    assert not session.nomination
    assert any_line_matches(output, "voted:.*Delta")
    assert any_line_matches(output, "voted:.*Golf")

def test_swap_seats():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["swap", [0, 1]])
    assert session.players[0].name == "Bravo"
    assert session.players[0].id == "PlayerID01"
    assert session.players[1].name == "Alpha"
    assert session.players[1].id == "PlayerID00"
    assert any_line_matches(output, "Alpha.*swapped")
    assert any_line_matches(output, "Bravo.*swapped")

def test_move_seats():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=8)
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["move", [1, 4]])
    assert [(p.name, p.id) for p in session.players] == \
        [("Alpha", "PlayerID00"),
         ("Charlie", "PlayerID02"),
         ("Delta", "PlayerID03"),
         ("Echo", "PlayerID04"),
         ("Bravo", "PlayerID01"),
         ("Foxtrot", "PlayerID05"),
         ("Golf", "PlayerID06"),
         ("Hotel", "PlayerID07")]
    assert any_line_matches(output, "Bravo.*moved.*4")
    output.clear()
    receive(session, ["move", [4, 1]])
    assert [p.name for p in session.players] == \
        ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"]
    assert any_line_matches(output, "Bravo.*moved.*1")

def test_take_vacate_retake_seat():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    gs["gamestate"][0]["id"] = ""
    gs["gamestate"][1]["id"] = ""
    receive(session, ["gs", gs])
    assert not any_line_matches(output, "PlayerID00")
    assert any_line_matches(output, "PlayerID02")
    output.clear()
    # This is signaled multiple ways; the one that townsquare
    # observes seems to be "player".
    # Here a player takes a seat, then vacates it and takes another.
    # We want to be sure the audit log shows these were in fact
    # the same client.
    receive(session, ["claim", [0, "PlayerID00"]])
    receive(session, ["player", dict(index=0, property="id", value="PlayerID00")])
    assert session.players[0].id == "PlayerID00"
    assert any_line_matches(output, "Alpha.*PlayerID00.*claimed")
    output.clear()
    receive(session, ["claim", [-1, "PlayerID00"]])
    receive(session, ["player", dict(index=0, property="id", value="")])
    assert session.players[0].id == ""
    assert any_line_matches(output, "Alpha.*PlayerID00.*left")
    output.clear()
    receive(session, ["claim", [1, "PlayerID00"]])
    receive(session, ["player", dict(index=1, property="id", value="PlayerID00")])
    assert session.players[1].id == "PlayerID00"
    assert any_line_matches(output, "Bravo.*PlayerID00.*claimed")

def test_ignore_ping():
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    # If you're curious, this is [user count, "latency"]
    receive(session, ["ping", [9, "69"]])
    receive(session, ["ping", [9, "420"]])
    receive(session, ["ping", [9, "47"]])

def test_organ_grinder_extension():
    # clocktower.live extension for Organ Grinder
    # No special handling really, but shouldn't break.
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs()
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["isVoteWatchingAllowed", False])
    receive(session, ["nomination", [0, 0]])
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [1, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [9, None]])
    receive(session, ["nomination", None])
    assert any_line_matches(output, r'voted:\s*$')

def test_banshee_extension():
    # clocktower.live extension for Banshee
    # No special handling really aside from not breaking on a 2 vote.
    session, output = simulated_session()
    receive(session, ["edition", {"edition": {"id": "tb"}}])
    gs = basic_gs(player_count=5)
    receive(session, ["gs", gs])
    output.clear()
    receive(session, ["player", dict(index=0, property="hasTwoVotes", value=True)])
    receive(session, ["votingSpeed", 1000])
    receive(session, ["nomination", [0, 0]])
    assert session.nomination == [0, 0]
    assert any_line_matches(output, "Alpha nominated Alpha")
    output.clear()
    receive(session, ["vote", [0, 2, False]])
    receive(session, ["lock", [0, None]])
    receive(session, ["isVoteInProgress", True])
    receive(session, ["lock", [1, None]])
    receive(session, ["lock", [2, None]])
    receive(session, ["lock", [3, None]])
    receive(session, ["lock", [4, None]])
    receive(session, ["lock", [5, None]])
    receive(session, ["lock", [6, 2]])
    receive(session, ["isVoteInProgress", False])
    receive(session, ["nomination", None])
    assert any_line_matches(output, r'voted.*Alpha$')
