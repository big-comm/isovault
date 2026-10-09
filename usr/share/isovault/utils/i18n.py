"""
Translation support using gettext.
"""

import gettext

gettext.textdomain("isovault")

_ = gettext.gettext
ngettext = gettext.ngettext
