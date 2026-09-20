# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared translation context for the whole plugin."""
from qgis.PyQt.QtCore import QCoreApplication

CONTEXT = 'EurekartoSvgTools'


def tr(text):
    return QCoreApplication.translate(CONTEXT, text)
