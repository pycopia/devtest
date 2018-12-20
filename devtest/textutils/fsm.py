# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
This module implements a generic finite state machine (FSM).
"""

import re

from devtest.core.types import NamedNumber, NamedNumberSet


class FSMError(Exception):
    pass


_cre = re.compile("test")
SREType = type(_cre)
del _cre

ANY = NamedNumber(-1, "ANY")


class FiniteStateMachine:
    """This class is a Finite State Machine (FSM).
    You set up a state transition table which is the association of:

        (input_symbol, current_state) --> (action, next_state)

    When the FSM matches a pair (current_state, input_symbol)
    it will call the associated action.
    The action is a function reference defined with a signature like this:

            def action(input_symbol, fsm)

    """
    ANY = ANY

    def __init__(self, initial_state=0):
        # (input_symbol, state) -> (action, next_state).
        self._transitions = {}
        self._expressions = []
        self.default_transition = None
        self.initial_state = initial_state
        self._reset()

    def push(self, v):
        self.stack.append(v)

    def pop(self):
        return self.stack.pop()

    def pushalt(self, v):
        self.altstack.append(v)

    def popalt(self):
        return self.altstack.pop()

    def _reset(self):
        """Rest the stacks and resets the current_state to the initial_state.
        """
        self.current_state = self.initial_state
        self.stack = []
        self.altstack = []

    def reset(self):
        """overrideable user reset."""
        self._reset()

    def is_reset(self):
        return self.current_state == self.initial_state

    def add_states(self, *args):
        for state in NamedNumberSet(map(str, args)):
            if not hasattr(self, str(state)):
                setattr(self, str(state), state)
            else:
                raise FSMError("state or attribute already exists.")

    def set_default_transition(self, action, next_state):
        if action is None and next_state is None:
            self.default_transition = None
        else:
            self.default_transition = (action, next_state)
    add_default_transition = set_default_transition  # alias

    def add_transition(self, input_symbol, state, action, next_state):
        """This adds an association between inputs and outputs.
                (input_symbol, current_state) --> (action, next_state)
        The action may be set to None.
        The input_symbol may be set to None.
        """
        self._transitions[(input_symbol, state)] = (action, next_state)

    def add_expression(self, expression, state, action, next_state, flags=0):
        """Adds a transition that activates if the input symbol matches the
        regular expression. The action callable gets a match object instead of
        the symbol.
        """
        cre = re.compile(expression, flags)
        self._expressions.append((cre, state, action, next_state))
        self._transitions[(SREType, state)] = (self._check_expression, None)

    def _check_expression(self, symbol, myself):
        for cre, state, action, next_state in self._expressions:
            mo = cre.match(symbol)
            if state is self.current_state and mo:
                if action is not None:
                    action(mo, self)
                self.current_state = next_state

    def add_transition_list(self, input_symbols, state, action, next_state):
        """This adds lots of the same transitions for different input symbols.
        You can pass a list or a string.
        """
        for input_symbol in input_symbols:
            self.add_transition(input_symbol, state, action, next_state)

    def get_transition(self, input_symbol, state):
        try:
            return self._transitions[(input_symbol, state)]
        except KeyError:
            try:
                return self._transitions[(ANY, state)]
            except KeyError:
                try:
                    return self._transitions[(SREType, state)]
                except KeyError:
                    # no expression matched, so check for default
                    if self.default_transition is not None:
                        return self.default_transition
                    else:
                        raise FSMError(
                            'Undefined transition {!r}.'.format(input_symbol))

    def process(self, input_symbol):
        """This causes the fsm to change state and call an action:
        `(input_symbol, current_state) --> (action, next_state)`.
        """
        action, next_state = self.get_transition(input_symbol,
                                                 self.current_state)
        if action is not None:
            action(input_symbol, self)
        if next_state is not None:
            self.current_state = next_state

    def process_string(self, s):
        for c in s:
            self.process(c)
