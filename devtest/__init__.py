# Reset the except hook to something sane on some Linux distros.
import sys
sys.excepthook = sys.__excepthook__
