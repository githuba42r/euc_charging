"""Test setup: expose the integration's modules without importing Home Assistant.

decoders.py uses package-relative imports (``from .const import ...``), so it
must be imported as part of a package. Importing ``custom_components.euc_charging``
would run its __init__.py, which needs Home Assistant. Instead, register a bare
package module pointing at the integration directory and alias the plain module
names the tests import.
"""

import importlib
import sys
import types
from pathlib import Path

_PKG_NAME = "euc_charging"
_PKG_DIR = Path(__file__).parent.parent / "custom_components" / _PKG_NAME

if _PKG_NAME not in sys.modules:
    pkg = types.ModuleType(_PKG_NAME)
    pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_PKG_NAME] = pkg

for _mod in ("const", "decoders"):
    sys.modules.setdefault(_mod, importlib.import_module(f"{_PKG_NAME}.{_mod}"))
