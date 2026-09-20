# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared translation context and text helpers for the whole plugin."""
from qgis.PyQt.QtCore import QCoreApplication

CONTEXT = 'EurekartoSvgTools'


def tr(text):
    return QCoreApplication.translate(CONTEXT, text)


def enum(owner, scope, name, legacy_owner=None, legacy_name=None):
    """Enum member, whether the build exposes it scoped, flat, or under its old name.

    QGIS 3.30 moved several enumerations into the Qgis namespace and Qt 6 dropped
    flat access to Qt enums; both spellings must keep working from QGIS 3.40 to
    QGIS 4.
    """
    holder = getattr(owner, scope, None)
    if holder is not None and hasattr(holder, name):
        return getattr(holder, name)
    if hasattr(owner, name):
        return getattr(owner, name)
    if legacy_owner is not None:
        return getattr(legacy_owner, legacy_name or name)
    raise AttributeError('{0}.{1} not found'.format(scope, name))


def number(value, precision):
    """Shortest fixed-point spelling, without a trailing zero or a negative zero."""
    text = '{:.{}f}'.format(value, precision)
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if text in ('', '-0') else text


def xml_text(text):
    """Escape the characters that cannot appear in XML text or in an attribute."""
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))
