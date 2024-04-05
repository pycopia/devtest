"""Functions that find and load test modules.
"""

from devtest import logging

from .. import importlib


def load_selections(selections):
    """Take a list of OptionSet objects and return a list of runnable
    objects, with options attached.

    Returns a tuple of found objects and errored object selections.
    """
    selist = []
    errlist = []
    for selection in selections:
        try:
            obj = importlib.get_object(selection.argument)
        except (ImportError, AttributeError) as ierr:
            logging.warning("Could not find: {}: {}".format(selection.argument, ierr))
            errlist.append(selection)
        else:
            if getattr(obj, "optionslist", None) is None:
                obj.optionslist = []
            obj.optionslist.append(selection.options)
            obj.version = None
            selist.append(obj)
    return selist, errlist
