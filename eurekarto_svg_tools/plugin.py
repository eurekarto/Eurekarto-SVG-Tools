# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""QGIS plugin lifecycle: translation, Processing provider, menu and toolbar."""
from pathlib import Path
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt 5
    from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication
from .common import tr
from .provider import EurekartoSvgToolsProvider

VERSION = '1.3.1'


class EurekartoSvgTools:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.provider = None
        self.translator = None
        self.menu = 'Eurekarto SVG Tools'
        self.directory = Path(__file__).resolve().parent
        settings = QSettings()
        override = settings.value('locale/overrideFlag', False, type=bool)
        locale = settings.value('locale/userLocale', 'en') if override else QLocale().name()
        if str(locale).lower().startswith('fr'):
            translator = QTranslator()
            if translator.load(str(self.directory / 'i18n' / 'eurekarto_svg_tools_fr.qm')):
                QCoreApplication.installTranslator(translator)
                self.translator = translator

    def initProcessing(self):
        self.provider = EurekartoSvgToolsProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        icon = QIcon(str(self.directory / 'img' / 'icon.png'))
        for title, callback, on_toolbar in [
                (tr('Map to grouped SVG'), self.run_export, True),
                (tr('About'), self.about, False)]:
            action = QAction(icon, title, self.iface.mainWindow())
            action.triggered.connect(callback)
            self.iface.addPluginToMenu(self.menu, action)
            if on_toolbar:
                self.iface.addToolBarIcon(action)
            self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
            action.deleteLater()
        self.actions.clear()
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
        if self.translator:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def run_export(self):
        from processing import execAlgorithmDialog
        execAlgorithmDialog('eurekartosvgtools:export_layout_svg', {})

    def about(self):
        QMessageBox.about(self.iface.mainWindow(), self.menu,
                          self.menu + ' ' + VERSION + '\n\n© 2026 Blanche Lambert / Eurêkarto\n' +
                          tr('Created by Blanche Lambert for Eurêkarto in 2026.') +
                          '\nGNU GPL v2 or later\nQGIS 3.40 LTR / QGIS 4.x')
