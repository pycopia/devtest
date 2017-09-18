"""Utils module for miscellaneous general functions.

Small functions can go right in here. Larger collections are found in modules
contained in the package.
"""


ViewType = type({}.keys())


def flatten(alist):
    """Flatten a list of lists or views.
    """
    rv = []
    for val in alist:
        if isinstance(val, (list, tuple)):
            rv.extend(flatten(val))
        elif isinstance(val, ViewType):
            rv.extend(flatten(list(val)))
        else:
            rv.append(val)
    return rv

