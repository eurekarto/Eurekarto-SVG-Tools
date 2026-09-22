# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""Layout items other than the map, painted by QGIS itself into SVG fragments.

A legend is not redrawn here: QGIS paints it into a QSvgGenerator and the
fragment is grafted into the document. That keeps its symbols, fonts, spacing
and frame identical to what the layout shows, at the price of depending on how
Qt writes SVG.
"""
import base64
import binascii
import math
import re
import sys
from contextlib import contextmanager

from qgis.PyQt.QtCore import QBuffer, QIODevice, QPointF, QRectF, QSize, QSizeF
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtSvg import QSvgGenerator
from qgis.PyQt.QtWidgets import QStyleOptionGraphicsItem
from qgis.core import (Qgis, QgsMapRendererCustomPainterJob, QgsMapSettings, QgsRenderContext,
                       QgsVectorLayer)

from .common import enum, number

# The fragment is painted at print resolution. Fonts are sized from the device
# resolution, so it must match the scale applied to the painter.
RESOLUTION = 300
DOTS_PER_MILLIMETRE = RESOLUTION / 25.4
# Room around the item for a frame stroke drawn half outside its rectangle.
MARGIN_MILLIMETRES = 2.0
# A rectangle covering this share of the canvas or more is a render background.
CANVAS_SHARE = 0.98
WRITE_ONLY = enum(QIODevice, 'OpenModeFlag', 'WriteOnly')
ANTIALIASING = enum(QPainter, 'RenderHint', 'Antialiasing')
DRAW_LABELING = enum(Qgis, 'MapSettingsFlag', 'DrawLabeling', QgsMapSettings, 'DrawLabeling')
SKIP_SYMBOLS = enum(Qgis, 'MapSettingsFlag', 'SkipSymbolRendering', QgsMapSettings,
                    'SkipSymbolRendering')
FORCE_VECTOR = enum(Qgis, 'MapSettingsFlag', 'ForceVectorOutput', QgsMapSettings,
                    'ForceVectorOutput')
PREMULTIPLIED = enum(QImage, 'Format', 'Format_ARGB32_Premultiplied')
# Opacity below which a pixel cannot be seen in print: 5 of 255, about 2 %.
VISIBLE_ALPHA = 5
# Premultiplied ARGB32 is stored as a native 32-bit word: alpha is the last byte
# on little-endian machines, the first on big-endian ones.
ALPHA_OFFSET = 3 if sys.byteorder == 'little' else 0
TEXT_AS_TEXT = enum(Qgis, 'TextRenderFormat', 'AlwaysText', QgsRenderContext,
                    'TextFormatAlwaysText')


def svg_device(width, height, margin=0.0):
    """A buffer and an SVG generator sized in pixels at print resolution."""
    buffer = QBuffer()
    buffer.open(WRITE_ONLY)
    generator = QSvgGenerator()
    generator.setOutputDevice(buffer)
    generator.setResolution(RESOLUTION)
    generator.setSize(QSize(width, height))
    generator.setViewBox(QRectF(-margin, -margin, width, height))
    return buffer, generator


def closed_content(buffer, canvas=None):
    """The generated drawing, tidied; canvas-sized backgrounds dropped when asked."""
    data = bytes(buffer.data())
    buffer.close()
    content = ''.join(fragment_content(data))
    if canvas is not None:
        content = without_backgrounds(content, *canvas)
    content = without_empty_groups(
        without_invisible_shapes(without_blank_images(content, canvas)))
    return [content] if content.strip() else []


GROUP = re.compile(r'<g\b([^>]*)>((?:(?!<g\b).)*?)</g>', re.S)
SHAPE = re.compile(r'<(?:rect|path)\b[^>]*/>')
MATRIX = re.compile(r'transform="matrix\(([^)]*)\)"')
NUMBER = re.compile(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')


def group_scale(attributes):
    """Horizontal and vertical scale of a group's transform; 1 without one."""
    match = MATRIX.search(attributes)
    if not match:
        return 1.0, 1.0
    try:
        a, b, c, d = [float(value) for value in match.group(1).split(',')[:4]]
    except ValueError:
        return 1.0, 1.0
    return math.hypot(a, b), math.hypot(c, d)


def shape_size(element):
    """Width and height a rect or path spans, in its own coordinates."""
    if element.startswith('<rect'):
        values = dict(re.findall(r'([\w:-]+)="([^"]*)"', element))
        try:
            return float(values.get('width', 0)), float(values.get('height', 0))
        except ValueError:
            return 0.0, 0.0
    data = re.search(r'\bd="([^"]*)"', element)
    numbers = [float(value) for value in NUMBER.findall(data.group(1))] if data else []
    xs, ys = numbers[0::2], numbers[1::2]
    if not xs or not ys:
        return 0.0, 0.0
    return max(xs) - min(xs), max(ys) - min(ys)


def without_backgrounds(content, width, height):
    """Drop shapes spanning the whole canvas, however the group scales them.

    A renderer lays a sheet under each of its passes — one per layer carrying
    labels. Some are transparent, some opaque white, and they sit in groups
    whose transform shrinks or enlarges them, so their written size alone does
    not reveal them: the size that counts is the one on the canvas. In a render
    of labels alone, no genuine shape covers the whole canvas.
    """
    def covers(element, scale):
        shape_width, shape_height = shape_size(element)
        return (shape_width * scale[0] >= width * CANVAS_SHARE
                and shape_height * scale[1] >= height * CANVAS_SHARE)

    def clean_group(match):
        scale = group_scale(match.group(1))
        inner = SHAPE.sub(lambda shape: '' if covers(shape.group(0), scale)
                          else shape.group(0), match.group(2))
        return '<g{0}>{1}</g>'.format(match.group(1), inner)

    def clean_loose(text):
        return SHAPE.sub(lambda shape: '' if covers(shape.group(0), (1.0, 1.0))
                         else shape.group(0), text)

    # Each shape is judged once, with the scale of the group that holds it:
    # shapes inside a group by that group's transform, the rest as written.
    pieces, last = [], 0
    for match in GROUP.finditer(content):
        pieces.append(clean_loose(content[last:match.start()]))
        pieces.append(clean_group(match))
        last = match.end()
    pieces.append(clean_loose(content[last:]))
    return ''.join(pieces)


def invisible(attributes):
    """True for a group whose shapes can show neither a fill nor a stroke."""
    values = dict(re.findall(r'([\w:-]+)="([^"]*)"', attributes))
    no_fill = values.get('fill') == 'none' or values.get('fill-opacity') in ('0', '0.0')
    no_stroke = values.get('stroke', 'none') == 'none' or values.get('stroke-opacity') in (
        '0', '0.0')
    return no_fill and no_stroke


def without_invisible_shapes(content):
    """Drop innermost groups that draw shapes nobody can see, and never any text.

    The renderer clears its canvas with transparent rectangles, one per pass.
    Qt writes them with a zero fill opacity, which Illustrator ignores and
    draws white. Judging by style rather than size catches every one of them.
    """
    def keep(match):
        if '<text' in match.group(2) or '<image' in match.group(2):
            return match.group(0)
        return '' if invisible(match.group(1)) else match.group(0)

    return GROUP.sub(keep, content)


EMBEDDED_PNG = re.compile(
    r'<image\b[^>]*?xlink:href="data:image/png;base64,([^"]*)"[^>]*/>', re.S)


def image_pixels(encoded):
    """The raw premultiplied ARGB bytes of an embedded PNG, or None if it cannot be read."""
    try:
        data = base64.b64decode(''.join(encoded.split()), validate=True)
    except (binascii.Error, ValueError):
        return None
    image = QImage.fromData(data, 'PNG')
    if image.isNull():
        return None
    image = image.convertToFormat(PREMULTIPLIED)
    size = image.sizeInBytes() if hasattr(image, 'sizeInBytes') else image.byteCount()
    bits = image.constBits()
    bits.setsize(size)
    return bits.asstring(size)


def blank(pixels):
    """True when no pixel reaches VISIBLE_ALPHA, so nothing can be seen in print.

    Every pixel's opacity is read, none is sampled: scaling the image down could
    lose a thin label. In premultiplied ARGB a pixel's colour never exceeds its
    opacity, so below that threshold the colour is invisible too.
    """
    alphas = pixels[ALPHA_OFFSET::4]
    return not alphas or max(alphas) < VISIBLE_ALPHA


def uniform(pixels):
    """True when every pixel is the same colour: the image carries no drawing."""
    return len(pixels) >= 4 and pixels == pixels[:4] * (len(pixels) // 4)


def blank_image(encoded):
    """True when an embedded PNG shows no pixel a reader could see."""
    pixels = image_pixels(encoded)
    return pixels is not None and blank(pixels)


def covers_canvas(tag, canvas):
    values = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
    try:
        return (float(values.get('width', 0)) >= canvas[0] * CANVAS_SHARE
                and float(values.get('height', 0)) >= canvas[1] * CANVAS_SHARE)
    except ValueError:
        return False


def without_blank_images(content, canvas=None):
    """Drop embedded images that carry nothing; keep every one that draws something.

    An image is dropped when no pixel is visible. With a canvas given — the
    labels render, where the labels themselves are text — an image covering the
    whole canvas in a single colour is dropped too: it is the flattened
    background of a layer QGIS could not blend into SVG, typically an opaque
    white sheet. An image that cannot be decoded is kept, not guessed.
    """
    def keep(match):
        pixels = image_pixels(match.group(1))
        if pixels is None:
            return match.group(0)
        if blank(pixels):
            return ''
        if canvas is not None and covers_canvas(match.group(0), canvas) and uniform(pixels):
            return ''
        return match.group(0)

    return EMBEDDED_PNG.sub(keep, content)


def without_empty_groups(content):
    """Drop groups and definitions left with nothing inside, nested ones included.

    Qt opens a group for every change of painter state, so a pass that draws
    nothing still leaves one behind.
    """
    empty = re.compile(r'<g\b[^>]*/>|<g\b[^>]*>\s*</g>|<defs\b[^>]*/>|<defs\b[^>]*>\s*</defs>')
    previous = None
    while previous != content:
        previous = content
        content = empty.sub('', content)
    return re.sub(r'\n\s*\n', '\n', content).strip()


def painted_fragment(item, millimetres_per_unit):
    """The item painted by QGIS, as SVG content in item millimetres times the resolution.

    The layout stays in its current render mode — its preview flag cannot be set
    from Python, and need not be: in preview, QgsLayoutItem.paint derives the
    resolution from the painter's transform, which is scaled here to print
    resolution, and only falls back to an image when the item carries advanced
    effects such as a blend mode.
    """
    rectangle = item.rect()
    scale = millimetres_per_unit * DOTS_PER_MILLIMETRE
    margin = MARGIN_MILLIMETRES * DOTS_PER_MILLIMETRE
    width = int(math.ceil(rectangle.width() * scale + 2 * margin))
    height = int(math.ceil(rectangle.height() * scale + 2 * margin))
    buffer, generator = svg_device(width, height, margin)
    context = item.layout().renderContext()
    painter = QPainter(generator)
    with text_kept_as_text(context):
        try:
            painter.setRenderHint(ANTIALIASING, True)
            painter.scale(scale, scale)
            item.paint(painter, QStyleOptionGraphicsItem(), None)
        finally:
            painter.end()
    return closed_content(buffer)


@contextmanager
def text_kept_as_text(context):
    """Have the layout write text as text objects, and restore its setting after.

    QgsLayoutRenderContext.setTextRenderFormat is public; without it a legend
    follows the layout's own export setting, which often outlines text.
    """
    reader = getattr(context, 'textRenderFormat', None)
    writer = getattr(context, 'setTextRenderFormat', None)
    previous = reader() if reader is not None and writer is not None else None
    if previous is not None:
        writer(TEXT_AS_TEXT)
    try:
        yield
    finally:
        if previous is not None:
            writer(previous)


def marker_fragment(symbol):
    """One marker symbol drawn by QGIS around the origin, in pixels at print resolution.

    Drawing it once per class and placing a copy at each point keeps every
    built-in shape, SVG marker and font marker exactly as QGIS draws it. Values
    driven by data — a size or a rotation read from a field — are not applied:
    each class shows its symbol as defined.
    """
    try:
        size = max(float(symbol.size()), 1.0)
    except (AttributeError, TypeError, ValueError):
        size = 5.0
    extent = int(math.ceil(size * 4 * DOTS_PER_MILLIMETRE))
    buffer, generator = svg_device(extent, extent, extent / 2.0)
    painter = QPainter(generator)
    try:
        painter.setRenderHint(ANTIALIASING, True)
        context = QgsRenderContext.fromQPainter(painter)
        text_format = getattr(context, 'setTextRenderFormat', None)
        if text_format is not None:
            text_format(TEXT_AS_TEXT)
        marker = symbol.clone()
        marker.startRender(context)
        try:
            marker.renderPoint(QPointF(0.0, 0.0), None, context)
        finally:
            marker.stopRender(context)
    finally:
        painter.end()
    return ''.join(closed_content(buffer))


def painted_labels(item, frame_size):
    """The map frame's labels, placed by QGIS's own engine, with no symbol drawn.

    The frame's own map settings are reused — layers, theme styles, rotation,
    labelling settings — at print resolution, so the labels land where the layout
    puts them. Symbols are skipped and rasters left out, which leaves the labels
    alone; text is kept as text so it can still be edited.
    """
    width = max(int(math.ceil(frame_size[0] * DOTS_PER_MILLIMETRE)), 1)
    height = max(int(math.ceil(frame_size[1] * DOTS_PER_MILLIMETRE)), 1)
    settings = item.mapSettings(item.extent(), QSizeF(width, height), RESOLUTION, True)
    settings.setLayers([layer for layer in settings.layers()
                        if isinstance(layer, QgsVectorLayer)])
    settings.setFlag(DRAW_LABELING, True)
    settings.setFlag(SKIP_SYMBOLS, True)
    # A layer with an opacity, a blend mode or effects is otherwise drawn into an
    # intermediate image of the whole canvas; symbols skipped, it stays empty but
    # is still written, and Illustrator shows it as a white sheet.
    settings.setFlag(FORCE_VECTOR, True)
    settings.setBackgroundColor(QColor(0, 0, 0, 0))
    text_format = getattr(settings, 'setTextRenderFormat', None)
    if text_format is not None:
        text_format(TEXT_AS_TEXT)
    buffer, generator = svg_device(width, height)
    painter = QPainter(generator)
    try:
        painter.setRenderHint(ANTIALIASING, True)
        job = QgsMapRendererCustomPainterJob(settings, painter)
        job.start()
        job.waitForFinished()
    finally:
        painter.end()
    return closed_content(buffer, canvas=(width, height))


def fragment_content(data):
    """What Qt drew, taken from between the generated root's tags.

    The generator's output has a known shape, so the drawing is sliced out as
    text rather than parsed: nothing here needs an XML parser. The fragment then
    inherits the document's own namespace. Qt's title and description go.
    """
    text = bytes(data).decode('utf-8')
    opening = text.find('<svg')
    start = text.find('>', opening) + 1 if opening >= 0 else 0
    end = text.rfind('</svg>')
    if opening < 0 or start <= 0 or end < start:
        return []
    inner = re.sub(r'<title>.*?</title>|<desc>.*?</desc>', '', text[start:end], flags=re.S)
    return [inner] if inner.strip() else []


def graft(identifier, label, placement, elements):
    """The fragment wrapped in a named group, placed on the page in millimetres.

    The fragment's coordinates are item millimetres times the resolution, so the
    group undoes that scale after applying the item's own placement.
    """
    if not elements:
        return []
    return (['<g id="{0}" data-name="{1}" transform="{2} scale({3})">'.format(
        identifier, label, placement, number(1.0 / DOTS_PER_MILLIMETRE, 9))]
        + elements + ['</g>'])
