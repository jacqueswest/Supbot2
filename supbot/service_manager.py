"""
service_manager.py

contains functions which performs operations (actions/checkers) on whatsapp app
they use `AppDriver` to perform it.

Checkers will get a rework to support other than `check_new_chat` eventually
"""
import re
import time
import typing
from typing import Tuple
from typeguard import check_type
from supbot.action import actions
from supbot.model import State, GUIState, Action, Event
from supbot.app_driver import AppDriver

if typing.TYPE_CHECKING:
    from supbot.api import System


# checker
def check_for_new_chat(system: 'System', driver: AppDriver,
                       current: GUIState) -> GUIState:
    """
    Checks for new chat on the main screen, first changes screen to main then uses driver to check it,
    if new chat is found, go into that chat and get the messages and call event for it

    :param system: `System` object
    :param driver: `AppDriver` object, used to perform operations on whatsapp gui
    :param current: data of current state of the app
    :return: resultant state of gui after operation
    """
    _, current = change_state(system, driver, current, GUIState(State.MAIN))
    chat = driver.get_new_chat()
    if chat is not None:
        _, current = change_state(system, driver, current, GUIState(State.CHAT, chat.name))
        messages = driver.get_new_messages()

        for m in messages:
            system.call_event(Event.MESSAGE_RECEIVED, (chat.name, m))
    return current


# action helper
def execute_action(system: 'System', driver: AppDriver, current: GUIState) -> GUIState:
    """
    Pop action from the buffer, and execute it, update the gui state
    :param system: `System` object
    :param driver: `AppDriver` object, used to perform operations on whatsapp gui
    :param current: current gui state
    :return: resultant state of gui after action is executed
    """
    try:
        action: Action = system.action_buffer.pop()
    except IndexError:
        return current

    meta = actions[action.name]

    try:
        check_type(action.name.name, action.data, meta.data_type)
    except TypeError:
        system.logger.warning("Action Data Typing incorrect for {} : got {} expected {}"
                              .format(action.name, action.data, meta.data_type))

        return current

    current = meta.run(driver, current, system, action.data)
    return current


def change_state(system: 'System', driver: AppDriver, _from: GUIState, _to: GUIState) -> Tuple[int, GUIState]:
    """
    meats of supbot brain, responsible for switching screen using a state machine
    performs appropriate actions on the gui to reach the target gui state
    Changes gui state and returns the updated state object depending on success or failure
    :param system: `System` object
    :param driver: AppDriver` object, used to perform operations on whatsapp gui
    :param _from: current gui state
    :param _to: target gui state
    :return: resultant state of gui after
    """
    if _to.state == State.MAIN:

        if _from.state == State.CHAT:
            driver.press_back()
            return 0, _to

    elif _to.state == State.CHAT:
        if _from.state == State.MAIN:

            if driver.click_on_chat(_to.info):
                return 0, _to
            system.logger.debug("Couldn't find chat {}, trying search bar".format(_to.info))
            if driver.search_chat(_to.info):
                if driver.click_on_chat(_to.info):
                    return 0, _to
                else:
                    system.logger.debug("Didn't find chat {} in search, trying intent".format(_to.info))
                    driver.press_back()
                    driver.press_back()

                    if re.search("\d{11,13}", _to.info):
                        # todo if by chance this halts in between it will mess up the states
                        if driver.search_chat("!temp") and driver.click_on_chat("!temp"):
                            if driver.type_and_send(f"wa.me/{_to.info}") and driver.click_on_last_chat_link():
                                if not driver.click_ok():
                                    return 0, _to
                                else:
                                    system.logger.debug("{} not found in Whatsapp".format(_to.info))
                            else:
                                system.logger.warning("This could lead to state mismatch, "
                                                      "if that happens contact the dev")
                                driver.press_back()
                        else:
                            system.logger.debug("Please create an empty group with `!temp` name")
                    else:
                        system.logger.debug("{} not a valid phone number".format(_to.info))

        elif _from.state == State.CHAT:
            if _from.info != _to.info:
                driver.press_back()
                return change_state(system, driver, GUIState(State.MAIN), _to)
            else:
                return 0, _to

    return 1, _from
