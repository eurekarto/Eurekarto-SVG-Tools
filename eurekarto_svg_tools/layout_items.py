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
from qgis.core import (Qgis, QgsLayoutRenderContext, QgsMapRendererCustomPainterJob,
                       QgsMapSettings, QgsRenderContext, QgsVectorLayer)

try:
    # Renders labels layer by layer in one pass. Absent from some builds, QGIS
    # 3.40 on macOS among them, where the blocking-region route below is used
    # instead. Importing it must never stop the plugin from loading.
    from qgis.core import QgsMapRendererStagedRenderJob
except ImportError:
    QgsMapRendererStagedRenderJob = None

try:
    from qgis.core import (QgsGeometry, QgsLabelBlockingRegion, QgsMapRendererParallelJob,
                           QgsPointXY)
except ImportError:
    QgsGeometry = QgsLabelBlockingRegion = QgsMapRendererParallelJob = QgsPointXY = None

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
# Without this, QGIS draws into an image any symbol it cannot compose as vectors —
# a layer opacity, a blend mode, a shadow, a shapeburst fill — and that image is
# what would land in the file. Its own SVG export sets the same flag.
FORCE_VECTOR_RENDER = enum(Qgis, 'RenderContextFlag', 'ForceVectorOutput',
                           QgsRenderContext, 'ForceVectorOutput')
FORCE_VECTOR_LAYOUT = enum(QgsLayoutRenderContext, 'Flag', 'FlagForceVectorOutput',
                           QgsLayoutRenderContext, 'FlagForceVectorOutput')


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
    with drawn_as_vectors(context):
        try:
            painter.setRenderHint(ANTIALIASING, True)
            painter.scale(scale, scale)
            item.paint(painter, QStyleOptionGraphicsItem(), None)
        finally:
            painter.end()
    return closed_content(buffer)


@contextmanager
def drawn_as_vectors(context):
    """Ask the layout for text objects and vector output, and restore its settings after.

    QgsLayoutRenderContext.setTextRenderFormat is public; without it a legend
    follows the layout's own export setting, which often outlines text. The
    vector flag keeps an item carrying an effect from being drawn into an image.
    """
    reader = getattr(context, 'textRenderFormat', None)
    writer = getattr(context, 'setTextRenderFormat', None)
    previous_format = reader() if reader is not None and writer is not None else None
    if previous_format is not None:
        writer(TEXT_AS_TEXT)
    flags = getattr(context, 'flags', None)
    set_flag = getattr(context, 'setFlag', None)
    previous_vector = None
    if flags is not None and set_flag is not None:
        previous_vector = bool(flags() & FORCE_VECTOR_LAYOUT)
        set_flag(FORCE_VECTOR_LAYOUT, True)
    try:
        yield
    finally:
        if previous_format is not None:
            writer(previous_format)
        if previous_vector is not None:
            set_flag(FORCE_VECTOR_LAYOUT, previous_vector)


IDENTITY = 'matrix(1,0,0,1,0,0)'
TAG = re.compile(r'<g\b([^>]*)>|</g>|<[^>]*>', re.S)
ATTRIBUTE = re.compile(r'([\w:-]+)="([^"]*)"')


def parse_groups(content):
    """The fragment as a tree of groups and leaves, or None if it is not balanced."""
    stack, attributes, position = [[]], [], 0
    for token in TAG.finditer(content):
        if token.start() > position:
            text = content[position:token.start()]
            if text.strip():
                stack[-1].append(('text', text, None))
        position = token.end()
        tag = token.group(0)
        if tag.startswith('<g'):
            attributes.append(token.group(1))
            stack.append([])
        elif tag == '</g>':
            if len(stack) == 1:
                return None
            children = stack.pop()
            stack[-1].append(('group', attributes.pop(), children))
        else:
            stack[-1].append(('leaf', tag, None))
    remainder = content[position:]
    if remainder.strip():
        stack[-1].append(('text', remainder, None))
    return stack[0] if len(stack) == 1 else None


def combine(outer, inner):
    """One set of attributes from two nested groups: the inner one wins, transforms stack."""
    values = dict(ATTRIBUTE.findall(outer))
    values.update(dict(ATTRIBUTE.findall(inner)))
    transforms = [one for one in (dict(ATTRIBUTE.findall(outer)).get('transform', ''),
                                  dict(ATTRIBUTE.findall(inner)).get('transform', ''))
                  if one and one.replace(' ', '') != IDENTITY]
    values.pop('transform', None)
    written = ['{0}="{1}"'.format(name, value) for name, value in values.items()]
    if transforms:
        written.insert(0, 'transform="{0}"'.format(' '.join(transforms)))
    return ' ' + ' '.join(written) if written else ''


PLAIN = {'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-opacity', 'stroke-width',
         'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'font-family', 'font-size',
         'font-weight', 'font-style', 'vector-effect'}


def dissolve(nodes):
    """Drop a style-only group whose children are all groups, pushing its style down.

    Qt opens one group carrying its painter defaults and puts every drawing
    inside it. It holds no transform, no clip and no opacity of its own, so its
    children can carry its attributes themselves and the level disappears.
    """
    result = []
    for node in nodes:
        kind, value, children = node
        if kind != 'group':
            result.append(node)
            continue
        children = dissolve(children)
        values = dict(ATTRIBUTE.findall(value))
        plain = values and set(values) <= PLAIN
        if plain and children and all(child[0] == 'group' for child in children):
            result += [('group', combine(value, child[1]), child[2]) for child in children]
        else:
            result.append(('group', value, children))
    return result


def fold(node):
    """A group holding nothing but one group becomes a single group."""
    kind, value, children = node
    if kind != 'group':
        return node
    folded = [fold(child) for child in children]
    if len(folded) == 1 and folded[0][0] == 'group':
        return ('group', combine(value, folded[0][1]), folded[0][2])
    return ('group', value, folded)


def write(nodes):
    out = []
    for kind, value, children in nodes:
        if kind == 'group':
            out.append('<g{0}>{1}</g>'.format(value, write(children)))
        else:
            out.append(value)
    return ''.join(out)


def flattened(content):
    """The same drawing with the empty nesting removed.

    Qt opens a group for its defaults and another for the painter state, so a
    single marker arrives three groups deep, and the group placing it on the map
    adds a fourth. Nothing is lost by merging them: a group holding one group
    only is the same drawing as its child carrying both sets of attributes.
    """
    nodes = parse_groups(content)
    if nodes is None:
        return content
    return write([fold(node) for node in dissolve(nodes)])


def single_group(content):
    """The attributes and contents of a fragment that is exactly one group, else None."""
    nodes = parse_groups(content)
    if nodes is None:
        return None
    groups = [node for node in nodes if node[0] == 'group']
    loose = [node for node in nodes if node[0] != 'group' and node[1].strip()]
    if len(groups) != 1 or loose:
        return None
    return groups[0][1], write(groups[0][2])


def placed_marker(fragment, placement):
    """The marker as a single group carrying its placement and its style."""
    return flattened('<g transform="{0}">{1}</g>'.format(placement, fragment))


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
        context.setFlag(FORCE_VECTOR_RENDER, True)
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
    return flattened(''.join(closed_content(buffer)))


def optional(owner, scope, name, legacy_owner, legacy_name):
    """An enumeration value, or None when this QGIS does not provide it."""
    if owner is None:
        return None
    try:
        return enum(owner, scope, name, legacy_owner, legacy_name)
    except (AttributeError, TypeError):
        return None


STAGE_LABELS = optional(QgsMapRendererStagedRenderJob, 'RenderStage', 'Labels',
                        QgsMapRendererStagedRenderJob, 'Labels')
LABELS_BY_LAYER = optional(QgsMapRendererStagedRenderJob, 'Flag', 'RenderLabelsByMapLayer',
                           QgsMapRendererStagedRenderJob, 'RenderLabelsByMapLayer')


def corner_points(position):
    """The four corners of a placed label, whatever the QGIS version calls them."""
    corners = getattr(position, 'cornerPoints', None)
    if callable(corners):
        corners = corners()
    return list(corners) if corners else []


def blocking_corners(positions, layer_id):
    """The corners of every label belonging to another layer.

    Declaring them as obstacles makes one layer's labels settle where the engine
    had put them when every layer was in play, which is what keeps a
    layer-by-layer render from colliding with itself.
    """
    blocked = []
    for position in positions:
        if getattr(position, 'layerID', None) == layer_id:
            continue
        corners = corner_points(position)
        if len(corners) >= 3:
            blocked.append(corners)
    return blocked


def label_positions(settings):
    """Where the engine places every label, with the layer each one comes from."""
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    results = job.takeLabelingResults()
    if results is None:
        return []
    labels = getattr(results, 'allLabels', None)
    return list(labels()) if labels is not None else []


def labels_by_blocking(item, frame_size):
    """Labels rendered one layer at a time, the other layers' labels blocking the way.

    A first pass over every layer asks the engine where each label goes. Each
    layer is then rendered alone with the other layers' labels declared as
    obstacles, so its own labels land where they did in the first pass.
    """
    if None in (QgsGeometry, QgsLabelBlockingRegion, QgsMapRendererParallelJob, QgsPointXY):
        raise RuntimeError('this QGIS cannot render labels layer by layer')
    settings, width, height = label_settings(item, frame_size)
    positions = label_positions(settings)
    if not positions:
        return []
    labelled = {getattr(position, 'layerID', None) for position in positions}
    drawings = []
    for layer in settings.layers():
        if layer.id() not in labelled:
            continue
        alone, _, _ = label_settings(item, frame_size)
        alone.setLayers([layer])
        alone.setLabelBlockingRegions(
            [QgsLabelBlockingRegion(QgsGeometry.fromPolygonXY([[QgsPointXY(point)
                                                                for point in corners]]))
             for corners in blocking_corners(positions, layer.id())])
        buffer, generator = svg_device(width, height)
        painter = QPainter(generator)
        try:
            painter.setRenderHint(ANTIALIASING, True)
            job = QgsMapRendererCustomPainterJob(alone, painter)
            job.start()
            job.waitForFinished()
        finally:
            painter.end()
        content = flattened(''.join(closed_content(buffer, canvas=(width, height))))
        if content.strip():
            drawings.append((layer.id(), content))
    return drawings


def labels_by_layer(item, frame_size):
    """The labels of each layer on its own, as (layer id, drawing) pairs.

    The staged job is the one QGIS uses to export a map as layered SVG: it hands
    back one part per layer, while the labelling engine still settles collisions
    across the whole map, which rendering each layer separately would lose.
    """
    if QgsMapRendererStagedRenderJob is None or STAGE_LABELS is None or LABELS_BY_LAYER is None:
        # No staged job here: block the other layers' labels instead.
        return labels_by_blocking(item, frame_size)
    settings, width, height = label_settings(item, frame_size)
    job = QgsMapRendererStagedRenderJob(settings, LABELS_BY_LAYER)
    job.start()
    drawings = []
    while not job.isFinished():
        if job.currentStage() == STAGE_LABELS:
            layer_id = job.currentLayerId()
            buffer, generator = svg_device(width, height)
            painter = QPainter(generator)
            try:
                painter.setRenderHint(ANTIALIASING, True)
                job.renderCurrentPart(painter)
            finally:
                painter.end()
            content = flattened(''.join(closed_content(buffer, canvas=(width, height))))
            if content.strip():
                drawings.append((layer_id, content))
        job.nextPart()
    return drawings


def label_settings(item, frame_size):
    """Map settings for a labels-only render of the map frame, and its pixel size."""
    width = max(int(math.ceil(frame_size[0] * DOTS_PER_MILLIMETRE)), 1)
    height = max(int(math.ceil(frame_size[1] * DOTS_PER_MILLIMETRE)), 1)
    settings = item.mapSettings(item.extent(), QSizeF(width, height), RESOLUTION, True)
    settings.setLayers([layer for layer in settings.layers()
                        if isinstance(layer, QgsVectorLayer)])
    settings.setFlag(DRAW_LABELING, True)
    settings.setFlag(SKIP_SYMBOLS, True)
    settings.setFlag(FORCE_VECTOR, True)
    settings.setBackgroundColor(QColor(0, 0, 0, 0))
    text_format = getattr(settings, 'setTextRenderFormat', None)
    if text_format is not None:
        text_format(TEXT_AS_TEXT)
    return settings, width, height


def painted_labels(item, frame_size):
    """Every label of the map frame in one drawing, when they cannot be split by layer."""
    settings, width, height = label_settings(item, frame_size)
    buffer, generator = svg_device(width, height)
    painter = QPainter(generator)
    try:
        painter.setRenderHint(ANTIALIASING, True)
        job = QgsMapRendererCustomPainterJob(settings, painter)
        job.start()
        job.waitForFinished()
    finally:
        painter.end()
    content = flattened(''.join(closed_content(buffer, canvas=(width, height))))
    return [content] if content.strip() else []


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
