"""Helper functions for unit tests. """

import runpy

def run_module(modulepath):
    runpy.run_module(modulepath, run_name="__main__", alter_sys=True)

