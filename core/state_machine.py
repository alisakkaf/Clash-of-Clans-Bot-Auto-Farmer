"""
State Machine — tracks the current game screen / phase.

Uses enum-based states with transition validation. Now includes
CONFIRMING state for the dynamic action-chain anti-stuck logic.
"""

from enum import Enum, auto

from core.logger import BotLogger

log = BotLogger.get("state")


class GameState(Enum):
    """All recognised game states."""
    UNKNOWN = auto()
    LOADING = auto()
    HOME = auto()
    CONFIRMING = auto()          # intermediate confirmation dialogs
    SEARCHING = auto()
    OPPONENT_FOUND = auto()
    IN_BATTLE = auto()
    BATTLE_ENDED = auto()
    DISCONNECTED = auto()
    # Builder Base specific
    BUILDER_BASE_HOME = auto()
    BB_CONFIRMING = auto()
    BB_SEARCHING = auto()
    BB_BATTLE = auto()
    BB_BATTLE_STAGE2 = auto()
    BB_BATTLE_ENDED = auto()


# Allowed transitions — used for sanity-check logging only
_VALID_TRANSITIONS: dict[GameState, set[GameState]] = {
    GameState.UNKNOWN:            {s for s in GameState},
    GameState.LOADING:            {GameState.HOME, GameState.BUILDER_BASE_HOME,
                                   GameState.DISCONNECTED, GameState.UNKNOWN},
    GameState.HOME:               {GameState.CONFIRMING, GameState.SEARCHING,
                                   GameState.LOADING, GameState.DISCONNECTED,
                                   GameState.BUILDER_BASE_HOME},
    GameState.CONFIRMING:         {GameState.SEARCHING, GameState.HOME,
                                   GameState.DISCONNECTED, GameState.CONFIRMING},
    GameState.SEARCHING:          {GameState.OPPONENT_FOUND, GameState.HOME,
                                   GameState.DISCONNECTED},
    GameState.OPPONENT_FOUND:     {GameState.IN_BATTLE, GameState.SEARCHING,
                                   GameState.DISCONNECTED},
    GameState.IN_BATTLE:          {GameState.BATTLE_ENDED, GameState.DISCONNECTED},
    GameState.BATTLE_ENDED:       {GameState.HOME, GameState.LOADING,
                                   GameState.DISCONNECTED},
    GameState.DISCONNECTED:       {s for s in GameState},
    GameState.BUILDER_BASE_HOME:  {GameState.BB_CONFIRMING, GameState.BB_SEARCHING,
                                   GameState.HOME, GameState.LOADING,
                                   GameState.DISCONNECTED},
    GameState.BB_CONFIRMING:      {GameState.BB_SEARCHING, GameState.BB_BATTLE,
                                   GameState.BUILDER_BASE_HOME, GameState.DISCONNECTED},
    GameState.BB_SEARCHING:       {GameState.BB_BATTLE, GameState.BUILDER_BASE_HOME,
                                   GameState.DISCONNECTED},
    GameState.BB_BATTLE:          {GameState.BB_BATTLE_STAGE2, GameState.BB_BATTLE_ENDED,
                                   GameState.DISCONNECTED},
    GameState.BB_BATTLE_STAGE2:   {GameState.BB_BATTLE_ENDED, GameState.DISCONNECTED},
    GameState.BB_BATTLE_ENDED:    {GameState.BUILDER_BASE_HOME, GameState.LOADING,
                                   GameState.DISCONNECTED},
}


class StateMachine:
    """Manages game state transitions with validation and logging."""

    def __init__(self) -> None:
        self._state = GameState.UNKNOWN
        log.info("State machine initialized -> %s", self._state.name)

    @property
    def state(self) -> GameState:
        return self._state

    def transition(self, new_state: GameState) -> None:
        """
        Move to *new_state*. Logs a warning (but does NOT block) if the
        transition is unexpected.
        """
        old = self._state
        if new_state == old:
            return

        valid = _VALID_TRANSITIONS.get(old, set())
        if new_state not in valid:
            log.warning(
                "Unexpected state transition: %s -> %s (allowed: %s)",
                old.name, new_state.name,
                ", ".join(s.name for s in valid),
            )
        self._state = new_state
        log.info("STATE CHANGE: %s -> %s", old.name, new_state.name)

    def is_battle(self) -> bool:
        return self._state in {
            GameState.IN_BATTLE, GameState.BB_BATTLE, GameState.BB_BATTLE_STAGE2,
        }

    def is_builder_base(self) -> bool:
        return self._state in {
            GameState.BUILDER_BASE_HOME, GameState.BB_CONFIRMING,
            GameState.BB_SEARCHING, GameState.BB_BATTLE,
            GameState.BB_BATTLE_STAGE2, GameState.BB_BATTLE_ENDED,
        }

    def is_confirming(self) -> bool:
        return self._state in {GameState.CONFIRMING, GameState.BB_CONFIRMING}

    def reset(self) -> None:
        log.info("State machine RESET -> UNKNOWN")
        self._state = GameState.UNKNOWN
