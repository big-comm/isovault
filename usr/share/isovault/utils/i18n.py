"""
Translation support using gettext.

Catalogs are looked up next to the application (usr/share/locale relative
to usr/share/isovault): the system directory once installed, the
repository's own catalogs when running from the source tree.
"""

import gettext
import os

LOCALE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locale"))

gettext.bindtextdomain("isovault", LOCALE_DIR)
gettext.textdomain("isovault")

_ = gettext.gettext
ngettext = gettext.ngettext
