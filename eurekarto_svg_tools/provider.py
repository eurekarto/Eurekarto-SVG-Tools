# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""Processing provider holding the plugin's algorithms."""
from pathlib import Path
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider
from .common import tr
from .svg_export import ExportLayoutSvg


class EurekartoSvgToolsProvider(QgsProcessingProvider):
    def id(self):
        return 'eurekartosvgtools'

    def name(self):
        return 'Eurekarto SVG Tools'

    def longName(self):
        return 'Eurekarto SVG Tools — ' + tr('Cartography for CAD')

    def icon(self):
        return QIcon(str(Path(__file__).resolve().parent / 'img' / 'icon.png'))

    def loadAlgorithms(self):
        self.addAlgorithm(ExportLayoutSvg())
