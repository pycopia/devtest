#! bash/zsh

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Some useful shell aliases when working with devtest or developing it, which is
# written in Python 3.

# Just modify (if needed) and source this file in your shell, or copy the
# contents to your startup file for your shell.

PYTHONBIN="/use/bin/python3.6"
alias py="$PYTHONBIN"
alias pi="$PYTHONBIN -iq"
alias pyrun="$PYTHONBIN -m"
alias pirun="$PYTHONBIN -iq -m"

PYTHONBIN2="/use/bin/python2.7"
alias py2="$PYTHONBIN2"
alias pi2="$PYTHONBIN2 -i"
alias pyrun2="$PYTHONBIN2 -m"
alias pirun2="$PYTHONBIN2 -i -m"
