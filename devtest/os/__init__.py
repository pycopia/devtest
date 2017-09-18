"""Operating system interfaces.

The modules in each platform specific sub-package should remain polymorphic with
each other.
"""

import sys
import os

__path__.append(os.path.join(__path__[0], sys.platform))
