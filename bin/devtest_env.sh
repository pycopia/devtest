#! bash/zsh

# Some useful shell aliases when working with devtest or developing it, which is
# written in Python 3.

# Just modify (if needed) and source this file in your shell, or copy the
# contents to your startup file for your shell.

PYTHONBIN="/use/bin/python3.5"
alias py="$PYTHONBIN"
alias pi="$PYTHONBIN -iq"
alias pyrun="$PYTHONBIN -m"
alias pirun="$PYTHONBIN -iq -m"

PYTHONBIN2="/use/bin/python2.7"
alias py2="$PYTHONBIN2"
alias pi2="$PYTHONBIN2 -i"
alias pyrun2="$PYTHONBIN2 -m"
alias pirun2="$PYTHONBIN2 -i -m"
