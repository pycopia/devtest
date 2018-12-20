# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Useful method decorators.
"""

import sys
from functools import wraps


def debugthis(meth):
    """Decorator for making methods enter the debugger on an exception."""
    @wraps(meth)
    def _lambda(*iargs, **ikwargs):
        try:
            return meth(*iargs, **ikwargs)
        except:  # noqa
            ex, val, tb = sys.exc_info()
            from devtest import debugger
            debugger.post_mortem(tb)
    return _lambda


if __name__ == "__main__":

    @debugthis
    def f():
        print("called f")
        raise KeyError("simulated key error")

    f()

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
