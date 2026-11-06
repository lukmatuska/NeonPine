#!/usr/bin/env python3
"""Start the NeonPine Companion from a source checkout: python3 neonpine-companion.py [--tray]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neonpine_companion.app import main  # noqa: E402

sys.exit(main())
