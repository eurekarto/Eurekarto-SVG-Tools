# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""Write a print layout map frame to a single grouped SVG file.

One <g> per layer, one <g> per symbology class, and — for the layers listed —
one named <g> per feature value, polygons optionally joined on an identifier
field. Raster layers are rendered by QGIS and embedded as PNG.

The SVG is written in millimetres at the page size, with the map group placed by
the map frame's own scene transform, so it overlays the layout's native SVG
export exactly.
"""
import math
import re
import unicodedata
from collections import namedtuple

from qgis.PyQt.QtCore import QBuffer, QIODevice, QSize, QSizeF, Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsCoordinateTransform, QgsExpressionContext, QgsExpressionContextUtils,
    QgsFeatureRequest, QgsGeometry, QgsLayoutItemMap, QgsLayoutItemRegistry,
    QgsMapRendererParallelJob, QgsMapSettings, QgsPointXY, QgsProcessing,
    QgsProcessingAlgorithm, QgsProcessingException, QgsProcessingParameterBoolean,
    QgsProcessingParameterField, QgsProcessingParameterFileDestination,
    QgsProcessingParameterLayout, QgsProcessingParameterLayoutItem,
    QgsProcessingParameterMatrix, QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber, QgsProcessingParameterVectorLayer, QgsRectangle,
    QgsRenderContext, QgsUnitTypes, QgsVariantUtils, QgsVectorLayer, QgsWkbTypes,
)

from .common import tr


def _enum(owner, scope, name, legacy_owner=None, legacy_name=None):
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


GEOMETRY_POLYGON = _enum(Qgis, 'GeometryType', 'Polygon', QgsWkbTypes, 'PolygonGeometry')
GEOMETRY_LINE = _enum(Qgis, 'GeometryType', 'Line', QgsWkbTypes, 'LineGeometry')
GEOMETRY_POINT = _enum(Qgis, 'GeometryType', 'Point', QgsWkbTypes, 'PointGeometry')
WKB_COLLECTION = _enum(Qgis, 'WkbType', 'GeometryCollection', QgsWkbTypes, 'GeometryCollection')
LAYOUT_MILLIMETRES = _enum(Qgis, 'LayoutUnit', 'Millimeters', QgsUnitTypes, 'LayoutMillimeters')
RENDER_MILLIMETRES = _enum(Qgis, 'RenderUnit', 'Millimeters', QgsUnitTypes, 'RenderMillimeters')
RENDER_POINTS = _enum(Qgis, 'RenderUnit', 'Points', QgsUnitTypes, 'RenderPoints')
RENDER_INCHES = _enum(Qgis, 'RenderUnit', 'Inches', QgsUnitTypes, 'RenderInches')
RENDER_PIXELS = _enum(Qgis, 'RenderUnit', 'Pixels', QgsUnitTypes, 'RenderPixels')
VECTOR_ANY_GEOMETRY = _enum(Qgis, 'ProcessingSourceType', 'VectorAnyGeometry',
                            QgsProcessing, 'TypeVectorAnyGeometry')
LAYOUT_MAP_ITEM = _enum(QgsLayoutItemRegistry, 'ItemType', 'LayoutMap')
PARAMETER_INTEGER = _enum(QgsProcessingParameterNumber, 'Type', 'Integer')
PARAMETER_DOUBLE = _enum(QgsProcessingParameterNumber, 'Type', 'Double')
NO_GEOMETRY_CHECK = _enum(QgsFeatureRequest, 'InvalidGeometryCheck', 'GeometryNoCheck')
REVERSE_TRANSFORM = _enum(QgsCoordinateTransform, 'TransformDirection', 'ReverseTransform')
TRANSFORM_SUCCESS = _enum(Qgis, 'GeometryOperationResult', 'Success')
NO_PEN = _enum(Qt, 'PenStyle', 'NoPen')
NO_BRUSH = _enum(Qt, 'BrushStyle', 'NoBrush')
WRITE_ONLY = _enum(QIODevice, 'OpenModeFlag', 'WriteOnly')

# Values that look like an ISO code but are "no data" markers. None of them is a
# valid ISO 3166 alpha-2 or alpha-3 code: 'NA' (Namibia) is deliberately absent.
PLACEHOLDER_IDS = frozenset({'-99', '-999', 'N/A', '#N/A', 'NULL', 'NONE', 'UNKNOWN'})

# Largest image accepted, so a high DPI on a large page cannot exhaust memory.
MAXIMUM_PIXELS = 60000000
# Douglas-Peucker tolerances tried when a shape holds more vertices than the
# limit: 0.01 mm on the page, doubled up to roughly 80 mm.
FIRST_TOLERANCE = 0.01
TOLERANCE_STEPS = 14

Options = namedtuple('Options', 'use_style clip raster_dpi default_radius')

# Counting keys for dropped features; translated only when the log line is built.
OUTSIDE, REPROJECTION, INVALID, TOO_SMALL, UNSYMBOLIZED = (
    'outside', 'reprojection', 'invalid', 'small', 'symbology')


def reason_label(key):
    return {OUTSIDE: tr('outside the frame'),
            REPROJECTION: tr('reprojection failed'),
            INVALID: tr('unrepairable geometry'),
            TOO_SMALL: tr('below the minimum area'),
            UNSYMBOLIZED: tr('not drawn by the symbology')}[key]


def number(value, precision):
    """Shortest fixed-point spelling, without a trailing zero or a negative zero."""
    text = '{:.{}f}'.format(value, precision)
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if text in ('', '-0') else text


def xml_text(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def xml_identifier(text, used):
    """XML id: ASCII, no reserved characters, never starting with a digit, unique."""
    decomposed = unicodedata.normalize('NFKD', text)
    folded = ''.join(one for one in decomposed if not unicodedata.combining(one))
    cleaned = re.sub(r'[^0-9A-Za-z_.-]+', '_', folded).strip('_')
    if not cleaned:
        cleaned = 'groupe'
    if not (cleaned[0].isalpha() or cleaned[0] == '_'):
        cleaned = '_' + cleaned
    cleaned = cleaned[:200]
    candidate, counter = cleaned, 2
    while candidate.casefold() in used:
        candidate = '{0}_{1}'.format(cleaned, counter)
        counter += 1
    used.add(candidate.casefold())
    return candidate


def field_text(value):
    """Readable, whitespace-collapsed text for a field value; empty when null."""
    if value is None or QgsVariantUtils.isNull(value):
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return ' '.join(str(value).split())


def keep_type(geometry, geometry_type):
    """Drop what repair or intersection leaves behind: slivers, points, collections."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return None
    collection = QgsWkbTypes.flatType(geometry.wkbType()) == WKB_COLLECTION
    if geometry.type() == geometry_type and not collection:
        return geometry
    parts = [part for part in geometry.asGeometryCollection()
             if not part.isEmpty() and part.type() == geometry_type]
    if not parts:
        return None
    result = QgsGeometry.collectGeometry(parts)
    return None if result.isNull() or result.isEmpty() else result


class FrameWriter:
    """Maps map coordinates to millimetres inside the frame and writes SVG shapes.

    The mapping is derived from the frame's own corners in map coordinates, so map
    rotation is carried without any trigonometry here.
    """

    def __init__(self, corners, size, crs, precision, split_parts, min_area, max_vertices):
        self.crs = crs
        self.precision = precision
        self.split_parts = split_parts
        self.min_area = min_area
        self.max_vertices = max_vertices
        self.width, self.height = size
        top_left = (corners[0].x(), corners[0].y())
        top_right = (corners[1].x(), corners[1].y())
        bottom_left = (corners[3].x(), corners[3].y())
        self.origin = top_left
        self.ux = (top_right[0] - top_left[0]) / self.width
        self.uy = (top_right[1] - top_left[1]) / self.width
        self.vx = (bottom_left[0] - top_left[0]) / self.height
        self.vy = (bottom_left[1] - top_left[1]) / self.height
        self.determinant = self.ux * self.vy - self.vx * self.uy
        if abs(self.determinant) < 1e-12:
            raise ValueError('degenerate frame')
        # Map units per millimetre on the page, so tolerances stay in millimetres.
        self.unit_mm = math.sqrt(abs(self.determinant))
        ring = [QgsPointXY(point.x(), point.y()) for point in corners]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        self.mask = QgsGeometry.fromPolygonXY([ring])
        self.extent = QgsRectangle(
            min(point.x() for point in corners), min(point.y() for point in corners),
            max(point.x() for point in corners), max(point.y() for point in corners))

    def to_frame(self, point):
        """Map coordinates to millimetres from the frame's top-left corner."""
        dx = point.x() - self.origin[0]
        dy = point.y() - self.origin[1]
        return ((self.vy * dx - self.vx * dy) / self.determinant,
                (self.ux * dy - self.uy * dx) / self.determinant)

    @staticmethod
    def ring_area(points):
        """Ring area in square millimetres, points already in frame coordinates."""
        total = 0.0
        for index in range(len(points)):
            x1, y1 = points[index]
            x2, y2 = points[(index + 1) % len(points)]
            total += x1 * y2 - x2 * y1
        return abs(total) / 2.0

    def path(self, points, closed):
        commands = []
        previous = None
        for x, y in points:
            current = (number(x, self.precision), number(y, self.precision))
            if current == previous:
                continue
            commands.append('{0},{1}'.format(*current))
            previous = current
        if closed and len(commands) > 1 and commands[0] == commands[-1]:
            commands.pop()
        if len(commands) < (3 if closed else 2):
            return ''
        return 'M' + commands[0] + 'L' + 'L'.join(commands[1:]) + ('Z' if closed else '')

    def vertex_count(self, geometry):
        """Vertices of the path that will be written: the heaviest part, or all."""
        try:
            if not self.split_parts:
                return geometry.constGet().nCoordinates()
            counts = [part.constGet().nCoordinates()
                      for part in geometry.asGeometryCollection()]
            return max(counts) if counts else 0
        except (AttributeError, TypeError, ValueError):
            return 0

    def reduce_vertices(self, geometry, geometry_type, stats):
        """Illustrator drops very dense paths: simplify until under the limit."""
        if not self.max_vertices or geometry_type == GEOMETRY_POINT:
            return geometry
        if self.vertex_count(geometry) <= self.max_vertices:
            return geometry
        tolerance, best = FIRST_TOLERANCE, None
        for _ in range(TOLERANCE_STEPS):
            candidate = keep_type(geometry.simplify(tolerance * self.unit_mm), geometry_type)
            if candidate is not None and not candidate.isGeosValid():
                candidate = keep_type(candidate.makeValid(), geometry_type)
            if candidate is not None:
                best = candidate
                if self.vertex_count(candidate) <= self.max_vertices:
                    stats['simplified'] += 1
                    stats['tolerance'] = max(stats['tolerance'], tolerance)
                    return candidate
            tolerance *= 2
        # Still too dense: the closest attempt is better than a shape Illustrator
        # will not open at all.
        stats['over'] += 1
        return best if best is not None else geometry

    def polygon_pieces(self, geometry):
        pieces, small = [], 0
        for polygon in geometry.asMultiPolygon():
            rings = [[self.to_frame(point) for point in ring] for ring in polygon]
            if not rings or self.ring_area(rings[0]) < self.min_area:
                small += 1
                continue
            drawn = [one for one in (self.path(ring, True) for ring in rings) if one]
            if drawn:
                pieces.append('<path d="{0}"/>'.format(''.join(drawn)))
        if not self.split_parts and len(pieces) > 1:
            merged = ''.join(re.findall(r'd="([^"]*)"', ''.join(pieces)))
            pieces = ['<path d="{0}"/>'.format(merged)]
        return pieces, small

    def line_pieces(self, geometry):
        pieces = []
        for line in geometry.asMultiPolyline():
            drawn = self.path([self.to_frame(point) for point in line], False)
            if drawn:
                pieces.append('<path d="{0}"/>'.format(drawn))
        return pieces

    def point_pieces(self, geometry, radius):
        pieces = []
        for point in geometry.asMultiPoint():
            x, y = self.to_frame(point)
            pieces.append('<circle cx="{0}" cy="{1}" r="{2}"/>'.format(
                number(x, self.precision), number(y, self.precision), number(radius, 3)))
        return pieces

    def pieces(self, geometry, geometry_type, radius, stats):
        """SVG elements for one geometry, plus the parts below the minimum area."""
        geometry = self.reduce_vertices(geometry, geometry_type, stats)
        geometry.convertToMultiType()
        if geometry_type == GEOMETRY_POLYGON:
            return self.polygon_pieces(geometry)
        if geometry_type == GEOMETRY_LINE:
            return self.line_pieces(geometry), 0
        return self.point_pieces(geometry, radius), 0


class ExportLayoutSvg(QgsProcessingAlgorithm):
    LAYOUT = 'LAYOUT'
    MAP_ITEM = 'MAP_ITEM'
    LAYERS = 'LAYERS'
    GROUP_LAYER = 'GROUP_LAYER'
    GROUP_NAME_FIELD = 'GROUP_NAME_FIELD'
    GROUP_JOIN_FIELD = 'GROUP_JOIN_FIELD'
    NAMING = 'NAMING'
    STYLE = 'STYLE'
    RASTERS = 'RASTERS'
    RASTER_DPI = 'RASTER_DPI'
    CLIP = 'CLIP'
    MIN_AREA = 'MIN_AREA'
    PRECISION = 'PRECISION'
    POINT_RADIUS = 'POINT_RADIUS'
    SPLIT_PARTS = 'SPLIT_PARTS'
    MAX_VERTICES = 'MAX_VERTICES'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'export_layout_svg'

    def displayName(self):
        return tr('Map to grouped SVG')

    def group(self):
        return tr('Cartography for CAD')

    def groupId(self):
        return 'cartography_for_cad'

    def createInstance(self):
        return ExportLayoutSvg()

    def flags(self):
        # Layout and project objects must only be accessed from the main thread.
        return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading

    def shortHelpString(self):
        return tr(
            '<p>Writes a whole map frame to one SVG file: one group per layer, in '
            'map order, ready to open in Illustrator or Inkscape.</p>'
            '<p><b>Named groups.</b> Choose a layer and the field that names its '
            'features — each value becomes a named group, so countries arrive as '
            '"France", "Spain" and so on instead of anonymous paths. The grouping '
            'field (optional) merges the polygons sharing a value into a single '
            'shape: with an ISO code, a country and its islands become one object. '
            'Codes are compared without case or spaces, and no-data codes (-99, N/A, '
            'NULL) fall back to the name, so unrelated territories stay apart. Use '
            'the table below for further layers.</p>'
            '<p><b>Colours.</b> Fills, outlines and widths are read from the layer '
            'symbology, and each class of a categorized or graduated layer becomes '
            'its own group named after its legend label, with named features nested '
            'inside. Layers with no outline in QGIS get none here. Only the first '
            'level of each symbol is read, so hatches, gradients and marker shapes '
            'come out as plain fills to restyle. Rasters are rendered by QGIS and '
            'embedded as images.</p>'
            '<p><b>Alignment.</b> The file is written in millimetres at the page '
            'size, with the map placed where the frame sits, so it can be pasted in '
            'place over the layout own SVG export — which carries the labels and the '
            'page furniture this algorithm does not export. Geometries are repaired '
            'and cut at the frame edge, so the file holds no clipping mask.</p>'
            '<p>Shapes holding more vertices than the limit are simplified, because '
            'Illustrator does not open very dense paths. The log reports the '
            'alignment values it read, the classes and groups written, the shapes '
            'simplified and every feature dropped, by cause.</p>')

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterLayout(
            self.LAYOUT, tr('Print layout')))
        self.addParameter(QgsProcessingParameterLayoutItem(
            self.MAP_ITEM, tr('Map frame'), parentLayoutParameterName=self.LAYOUT,
            itemType=LAYOUT_MAP_ITEM))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.LAYERS, tr('Layers to export (empty = those shown in the frame)'),
            VECTOR_ANY_GEOMETRY, optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.GROUP_LAYER, tr('Layer to split into named groups (e.g. countries)'),
            optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.GROUP_NAME_FIELD, tr('Field holding the names'),
            parentLayerParameterName=self.GROUP_LAYER, optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.GROUP_JOIN_FIELD, tr('Field grouping the polygons (e.g. ISO code)'),
            parentLayerParameterName=self.GROUP_LAYER, optional=True))
        self.addParameter(QgsProcessingParameterMatrix(
            self.NAMING, tr('Other layers to name (layer, name field, grouping field)'),
            numberRows=1,
            headers=[tr('Layer'), tr('Name field'), tr('Grouping field')],
            defaultValue=['', '', ''], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.STYLE, tr('Keep the colours and classes from QGIS'), defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.RASTERS, tr('Embed images (rasters)'), defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.RASTER_DPI, tr('Image resolution (DPI)'), PARAMETER_INTEGER,
            defaultValue=200, minValue=36, maxValue=1200))
        self.addParameter(QgsProcessingParameterBoolean(
            self.CLIP, tr('Cut at the frame edge'), defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_AREA, tr('Minimum polygon area (mm² on the page)'),
            PARAMETER_DOUBLE, defaultValue=0.05, minValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.PRECISION, tr('Coordinate precision (decimals)'), PARAMETER_INTEGER,
            defaultValue=3, minValue=0, maxValue=9))
        self.addParameter(QgsProcessingParameterNumber(
            self.POINT_RADIUS, tr('Default point size (mm)'), PARAMETER_DOUBLE,
            defaultValue=0.8, minValue=0.01))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SPLIT_PARTS, tr('Separate islands into distinct paths'),
            defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_VERTICES, tr('Maximum vertices per shape (0 = no limit)'),
            PARAMETER_INTEGER, defaultValue=10000, minValue=0, maxValue=10000000))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, tr('SVG file'), fileFilter='SVG (*.svg)'))

    # ------------------------------------------------------------------ symbology

    @staticmethod
    def render_millimetres(value, unit):
        """Symbol size to millimetres; None when the unit depends on the map."""
        factors = {RENDER_MILLIMETRES: 1.0, RENDER_POINTS: 25.4 / 72.0,
                   RENDER_INCHES: 25.4, RENDER_PIXELS: 25.4 / 96.0}
        factor = factors.get(unit)
        return None if factor is None else value * factor

    @staticmethod
    def pen_is_none(symbol_layer):
        """True when QGIS draws no outline at all (pen style set to no pen)."""
        for reader in ('strokeStyle', 'penStyle'):
            if hasattr(symbol_layer, reader):
                try:
                    if getattr(symbol_layer, reader)() == NO_PEN:
                        return True
                except (AttributeError, TypeError):
                    continue
        return False

    @staticmethod
    def brush_is_none(symbol_layer):
        """True when QGIS draws no fill at all (brush style set to no brush)."""
        if hasattr(symbol_layer, 'brushStyle'):
            try:
                return symbol_layer.brushStyle() == NO_BRUSH
            except (AttributeError, TypeError):
                return False
        return False

    @staticmethod
    def stroke_attributes(colour, width, hairline=0.03):
        """Stroke attributes, or stroke="none". Width 0 is a hairline in QGIS."""
        if colour is None or colour.alphaF() <= 0:
            return ['stroke="none"']
        attributes = ['stroke="{0}"'.format(colour.name()),
                      'stroke-width="{0}"'.format(
                          number(width if width and width > 0 else hairline, 3))]
        if colour.alphaF() < 0.999:
            attributes.append('stroke-opacity="{0}"'.format(number(colour.alphaF(), 3)))
        return attributes

    @staticmethod
    def fill_attributes(colour, opacity, no_brush):
        if no_brush:
            return ['fill="none"']
        attributes = ['fill="{0}"'.format(colour.name())]
        if opacity < 0.999:
            attributes.append('fill-opacity="{0}"'.format(number(opacity, 3)))
        return attributes

    def outline_of(self, symbol_layer):
        """Outline colour and width in millimetres, or (None, None) when absent."""
        if symbol_layer is None or self.pen_is_none(symbol_layer):
            return None, None
        colour, width = None, None
        if hasattr(symbol_layer, 'strokeColor'):
            try:
                colour = symbol_layer.strokeColor()
            except (AttributeError, TypeError):
                colour = None
        if hasattr(symbol_layer, 'strokeWidth'):
            try:
                unit = getattr(symbol_layer, 'strokeWidthUnit', lambda: None)()
                width = self.render_millimetres(symbol_layer.strokeWidth(), unit)
            except (AttributeError, TypeError):
                width = None
        return colour, width

    @staticmethod
    def default_style(geometry_type, radius):
        if geometry_type == GEOMETRY_POLYGON:
            return 'fill="#cccccc" stroke="none"', radius
        if geometry_type == GEOMETRY_LINE:
            return 'fill="none" stroke="#000000" stroke-width="0.2"', radius
        return 'fill="#000000" stroke="none"', radius

    def line_style(self, symbol, colour, fill_opacity, first, radius):
        if first is not None and self.pen_is_none(first):
            return 'fill="none" stroke="none"', radius
        try:
            width = self.render_millimetres(symbol.width(), symbol.outputUnit())
        except (AttributeError, TypeError):
            width = None
        stroke_colour, _ = self.outline_of(first)
        line_colour = stroke_colour if stroke_colour is not None else colour
        attributes = ['fill="none"'] + self.stroke_attributes(line_colour, width or 0.2)
        if fill_opacity < 0.999 and line_colour.alphaF() >= 0.999:
            attributes.append('stroke-opacity="{0}"'.format(number(fill_opacity, 3)))
        return ' '.join(attributes), radius

    def style_of(self, symbol, geometry_type, default_radius):
        """SVG presentation attributes and point radius read from a QGIS symbol."""
        radius = default_radius
        if symbol is None:
            return self.default_style(geometry_type, radius)
        try:
            opacity = float(symbol.opacity())
        except (AttributeError, TypeError, ValueError):
            opacity = 1.0
        colour = symbol.color()
        fill_opacity = opacity * colour.alphaF()
        first = symbol.symbolLayer(0) if symbol.symbolLayerCount() else None
        if geometry_type == GEOMETRY_LINE:
            return self.line_style(symbol, colour, fill_opacity, first, radius)
        if geometry_type == GEOMETRY_POINT:
            try:
                size = self.render_millimetres(symbol.size(), symbol.sizeUnit())
                if size and size > 0:
                    radius = size / 2.0
            except (AttributeError, TypeError):
                pass
        no_brush = first is not None and self.brush_is_none(first)
        stroke_colour, stroke_width = self.outline_of(first)
        attributes = (self.fill_attributes(colour, fill_opacity, no_brush)
                      + self.stroke_attributes(stroke_colour, stroke_width))
        return ' '.join(attributes), radius

    # ---------------------------------------------------------------- layout read

    @staticmethod
    def to_millimetres(layout, length):
        """Layout units are usually millimetres, but never assume it."""
        try:
            return layout.convertFromLayoutUnits(length, LAYOUT_MILLIMETRES).length()
        except (AttributeError, TypeError):
            return length

    def placement_of(self, layout, item, page):
        """SVG transform placing the frame on the page, item rotation included.

        Taken from the item's scene transform, whose linear part is unitless and
        whose translation is converted to millimetres: a rotated frame then lands
        where QGIS draws it, and not where a rotation about its corner would put it.
        """
        try:
            transform = item.sceneTransform()
            origin = page.scenePos()
            return 'matrix({0},{1},{2},{3},{4},{5})'.format(
                number(transform.m11(), 9), number(transform.m12(), 9),
                number(transform.m21(), 9), number(transform.m22(), 9),
                number(self.to_millimetres(layout, transform.dx() - origin.x()), 3),
                number(self.to_millimetres(layout, transform.dy() - origin.y()), 3))
        except (AttributeError, TypeError):
            offset = item.scenePos() - page.scenePos()
            return 'translate({0},{1})'.format(
                number(self.to_millimetres(layout, offset.x()), 3),
                number(self.to_millimetres(layout, offset.y()), 3))

    def frame_of(self, layout, item, feedback):
        """Page size, frame size, placement and CRS, all read from the layout."""
        width = self.to_millimetres(layout, item.rect().width())
        height = self.to_millimetres(layout, item.rect().height())
        if width <= 0 or height <= 0:
            raise QgsProcessingException(tr('The map frame has no size.'))
        page = layout.pageCollection().page(max(item.page(), 0))
        if page is None:
            raise QgsProcessingException(tr('The map frame is not on a page.'))
        # Top-left, top-right, bottom-right, bottom-left of the frame, in map units.
        corners = item.visibleExtentPolygon()
        if len(corners) < 4:
            raise QgsProcessingException(
                tr('Could not read the area shown by the map frame.'))
        if not item.crs().isValid():
            raise QgsProcessingException(
                tr('The map frame has no coordinate reference system.'))
        frame = {
            'crs': item.crs(), 'corners': corners, 'size': (width, height),
            'page': (self.to_millimetres(layout, page.rect().width()),
                     self.to_millimetres(layout, page.rect().height())),
            'placement': self.placement_of(layout, item, page),
            'map_rotation': item.mapRotation(),
        }
        feedback.pushInfo(tr(
            'Layout "{0}": page {1} x {2} mm, frame {3} x {4} mm, placement {5}, map '
            'rotation {6}°, scale 1:{7}, CRS {8}.').format(
                layout.name(), number(frame['page'][0], 2), number(frame['page'][1], 2),
                number(width, 2), number(height, 2), frame['placement'],
                number(item.mapRotation(), 3), number(item.scale(), 0),
                item.crs().authid()))
        return frame

    def layers_of(self, parameters, context, item, feedback):
        """Explicit list, or exactly what the map frame renders, bottom layer first."""
        keep_rasters = self.parameterAsBool(parameters, self.RASTERS, context)
        layers = self.parameterAsLayerList(parameters, self.LAYERS, context)
        if not layers:
            try:
                layers = item.layersToRender()
            except (AttributeError, TypeError):
                layers = item.layers()
            if not layers and context.project():
                layers = context.project().layerTreeRoot().layerOrder()
        kept = []
        for layer in layers:
            if layer is None or not layer.isValid():
                continue
            if not isinstance(layer, QgsVectorLayer) and not keep_rasters:
                feedback.pushWarning(tr(
                    'Layer "{0}" is not a vector layer and was skipped.').format(layer.name()))
                continue
            if layer.hasScaleBasedVisibility() and not layer.isInScaleRange(item.scale()):
                feedback.pushInfo(
                    tr('Layer "{0}" is hidden at this scale.').format(layer.name()))
                continue
            kept.append(layer)
        if not kept:
            raise QgsProcessingException(tr('No layer to export.'))
        # Layer lists run top to bottom; SVG paints in document order.
        kept.reverse()
        return kept

    def naming_of(self, parameters, context, layers):
        """Layer name (case-folded) -> (name field, join field), checked for real."""
        mapping = {}
        chosen = self.parameterAsVectorLayer(parameters, self.GROUP_LAYER, context)
        if chosen is not None:
            name_field = self.parameterAsString(parameters, self.GROUP_NAME_FIELD, context)
            join_field = self.parameterAsString(parameters, self.GROUP_JOIN_FIELD, context)
            if not name_field and not join_field:
                raise QgsProcessingException(tr(
                    'Choose a name field, a grouping field, or both, for layer '
                    '"{0}".').format(chosen.name()))
            mapping[chosen.name().casefold()] = (name_field, join_field)
        values = list(self.parameterAsMatrix(parameters, self.NAMING, context) or [])
        while len(values) % 3:
            values.append('')
        for index in range(0, len(values), 3):
            layer_name = field_text(values[index])
            name_field = field_text(values[index + 1])
            join_field = field_text(values[index + 2])
            if layer_name and (name_field or join_field):
                mapping[layer_name.casefold()] = (name_field, join_field)
        available = {layer.name().casefold(): layer for layer in layers}
        for layer_name, fields in mapping.items():
            layer = available.get(layer_name)
            if layer is None:
                raise QgsProcessingException(tr(
                    'Layer "{0}" is not among the exported layers. Available: {1}.').format(
                        layer_name, ', '.join(sorted(one.name() for one in layers))))
            for field in fields:
                if field and layer.fields().indexFromName(field) < 0:
                    raise QgsProcessingException(tr(
                        'Layer "{0}" has no field "{1}". Available fields: {2}.').format(
                            layer.name(), field, ', '.join(layer.fields().names())))
        return mapping

    @staticmethod
    def render_context_of(item, frame):
        """A render context carrying the real map scale, for rule-based renderers."""
        try:
            settings = item.mapSettings(
                item.extent(), QSizeF(frame['size'][0], frame['size'][1]), 96, False)
            return QgsRenderContext.fromMapSettings(settings)
        except (AttributeError, TypeError):
            context = QgsRenderContext()
            context.setExpressionContext(QgsExpressionContext())
            return context

    # -------------------------------------------------------------------- rasters

    def image_element(self, layer, item, frame, dpi, context, feedback):
        """Render a non-vector layer to a transparent PNG embedded in the SVG."""
        width_px = max(int(round(frame['size'][0] * dpi / 25.4)), 1)
        height_px = max(int(round(frame['size'][1] * dpi / 25.4)), 1)
        if width_px * height_px > MAXIMUM_PIXELS:
            raise QgsProcessingException(tr(
                'Layer "{0}" would render as {1} x {2} pixels: lower the image '
                'resolution.').format(layer.name(), width_px, height_px))
        settings = QgsMapSettings()
        settings.setLayers([layer])
        settings.setDestinationCrs(frame['crs'])
        settings.setExtent(item.extent())
        settings.setRotation(frame['map_rotation'])
        settings.setOutputSize(QSize(width_px, height_px))
        settings.setOutputDpi(dpi)
        settings.setBackgroundColor(QColor(0, 0, 0, 0))
        try:
            settings.setTransformContext(context.transformContext())
        except (AttributeError, TypeError):
            pass
        job = QgsMapRendererParallelJob(settings)
        job.start()
        job.waitForFinished()
        image = job.renderedImage()
        if image is None or image.isNull():
            feedback.pushWarning(tr('Layer "{0}" produced no image.').format(layer.name()))
            return None
        buffer = QBuffer()
        buffer.open(WRITE_ONLY)
        try:
            if not image.save(buffer, 'PNG'):
                feedback.pushWarning(
                    tr('Layer "{0}": could not encode the image.').format(layer.name()))
                return None
            encoded = bytes(buffer.data().toBase64()).decode('ascii')
        finally:
            buffer.close()
        feedback.pushInfo(tr(
            'Layer "{0}" embedded as an image, {1} x {2} px, {3} KB.').format(
                layer.name(), width_px, height_px, int(len(encoded) * 3 / 4096)))
        return ('<image x="0" y="0" width="{0}" height="{1}" preserveAspectRatio="none" '
                'xlink:href="data:image/png;base64,{2}"/>'.format(
                    number(frame['size'][0], 3), number(frame['size'][1], 3), encoded))

    # -------------------------------------------------------------- vector layers

    @staticmethod
    def request_for(layer, writer, context):
        """Feature request limited to the frame, plus the transform to the map CRS."""
        request = QgsFeatureRequest()
        request.setInvalidGeometryCheck(NO_GEOMETRY_CHECK)
        if layer.crs() == writer.crs:
            request.setFilterRect(writer.extent)
            return request, None
        transform = QgsCoordinateTransform(layer.crs(), writer.crs,
                                           context.transformContext())
        try:
            request.setFilterRect(
                transform.transformBoundingBox(writer.extent, REVERSE_TRANSFORM))
        except Exception:
            # An extent that cannot be expressed in the layer CRS: read it all.
            pass
        return request, transform

    @staticmethod
    def renderer_of(layer, render_context, use_style):
        """A started renderer clone and its legend labels, or (None, {})."""
        if not use_style or layer.renderer() is None:
            return None, {}
        renderer = layer.renderer().clone()
        render_context.setExpressionContext(QgsExpressionContext(
            QgsExpressionContextUtils.globalProjectLayerScopes(layer)))
        renderer.startRender(render_context, layer.fields())
        legend = {}
        try:
            for order, entry in enumerate(renderer.legendSymbolItems()):
                legend[entry.ruleKey()] = (order, entry.label())
        except (AttributeError, TypeError):
            legend = {}
        return renderer, legend

    @staticmethod
    def class_of(renderer, legend, feature, render_context):
        """(key, order, label, symbol); key None when the symbology draws nothing."""
        if renderer is None:
            return '', 0, '', None
        render_context.expressionContext().setFeature(feature)
        try:
            symbol = renderer.symbolForFeature(feature, render_context)
        except (AttributeError, TypeError):
            symbol = None
        if symbol is None:
            return None, 0, '', None
        try:
            keys = renderer.legendKeysForFeature(feature, render_context)
            key = sorted(keys)[0] if keys else ''
        except (AttributeError, TypeError):
            key = ''
        order, label = legend.get(key, (0, ''))
        return key, order, label, symbol

    @staticmethod
    def prepared_geometry(feature, geometry_type, transform, writer, clip, dropped):
        """Repaired, reprojected and clipped geometry, or None with a counted reason."""
        geometry = feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            dropped[INVALID] += 1
            return None
        geometry = QgsGeometry(geometry)
        if transform is not None:
            try:
                status = geometry.transform(transform)
            except Exception:
                status = None
            if status != TRANSFORM_SUCCESS:
                dropped[REPROJECTION] += 1
                return None
        geometry.convertToStraightSegment()
        if not geometry.isGeosValid():
            geometry = keep_type(geometry.makeValid(), geometry_type)
            if geometry is None:
                dropped[INVALID] += 1
                return None
        if clip:
            if not geometry.boundingBoxIntersects(writer.extent):
                dropped[OUTSIDE] += 1
                return None
            geometry = keep_type(geometry.intersection(writer.mask), geometry_type)
            if geometry is None:
                dropped[OUTSIDE] += 1
                return None
        return geometry

    @staticmethod
    def join_key(code, label):
        """Join on the identifier; placeholders and empties fall back to the name."""
        if code and code not in PLACEHOLDER_IDS:
            return 'code', code
        if label:
            return 'name', label.casefold()
        return 'code', code

    def class_slot(self, classes, key, order, label, symbol, geometry_type, options):
        """The slot collecting one symbology class, created with its style on first use."""
        if key not in classes:
            attributes, radius = self.style_of(symbol, geometry_type, options.default_radius)
            classes[key] = {'order': order, 'label': label, 'groups': {},
                            'attributes': attributes, 'radius': radius, 'flat': []}
        return classes[key]

    @classmethod
    def hold_for_join(cls, pending, class_key, geometry, label, code):
        """Hold a geometry until every feature sharing its value has been read."""
        entry = pending.setdefault(
            (class_key, cls.join_key(code, label)),
            {'geometries': [], 'names': [], 'code': code, 'class': class_key})
        entry['geometries'].append(geometry)
        if label and label not in entry['names']:
            entry['names'].append(label)

    def collect(self, layer, writer, fields, options, render_context, context, feedback):
        """Group one vector layer's features by symbology class, then by name."""
        name_field, join_field = fields
        geometry_type = layer.geometryType()
        if join_field and geometry_type != GEOMETRY_POLYGON:
            feedback.pushWarning(
                tr('Layer "{0}" holds no polygons: grouping ignored.').format(layer.name()))
            join_field = ''
        renderer, legend = self.renderer_of(layer, render_context, options.use_style)
        request, transform = self.request_for(layer, writer, context)
        classes, pending = {}, {}
        dropped = {OUTSIDE: 0, REPROJECTION: 0, INVALID: 0, TOO_SMALL: 0, UNSYMBOLIZED: 0}
        stats = {'simplified': 0, 'over': 0, 'tolerance': 0.0}
        unnamed = tr('Unnamed')
        canceled = False
        try:
            for feature in layer.getFeatures(request):
                if feedback.isCanceled():
                    canceled = True
                    break
                key, order, class_label, symbol = self.class_of(
                    renderer, legend, feature, render_context)
                if key is None:
                    dropped[UNSYMBOLIZED] += 1
                    continue
                geometry = self.prepared_geometry(
                    feature, geometry_type, transform, writer, options.clip, dropped)
                if geometry is None:
                    continue
                slot = self.class_slot(classes, key, order, class_label, symbol,
                                       geometry_type, options)
                label = field_text(feature[name_field]) if name_field else ''
                if join_field:
                    self.hold_for_join(pending, key, geometry, label,
                                       field_text(feature[join_field]).upper())
                    continue
                pieces, small = writer.pieces(geometry, geometry_type, slot['radius'], stats)
                if not pieces:
                    dropped[TOO_SMALL if small else INVALID] += 1
                    continue
                if name_field:
                    slot['groups'].setdefault(label or unnamed, []).extend(pieces)
                else:
                    slot['flat'].extend(pieces)
            if self.merge_pending(layer, pending, classes, writer, geometry_type,
                                  dropped, stats, unnamed, feedback):
                canceled = True
        finally:
            if renderer is not None:
                try:
                    renderer.stopRender(render_context)
                except (AttributeError, TypeError):
                    pass
        self.report(layer, dropped, stats, feedback)
        return classes, canceled

    def merge_pending(self, layer, pending, classes, writer, geometry_type, dropped,
                      stats, unnamed, feedback):
        """Union the geometries grouped on the join field: one shape per value."""
        for entry in pending.values():
            if feedback.isCanceled():
                return True
            if len(entry['names']) > 1:
                feedback.pushWarning(tr(
                    'Layer "{0}": value {1} covers several names ({2}); the first '
                    'is used.').format(layer.name(), entry['code'] or '-',
                                       ', '.join(entry['names'])))
            joined = (entry['geometries'][0] if len(entry['geometries']) == 1
                      else QgsGeometry.unaryUnion(entry['geometries']))
            joined = keep_type(joined, geometry_type)
            if joined is None:
                dropped[INVALID] += 1
                continue
            slot = classes[entry['class']]
            pieces, small = writer.pieces(joined, geometry_type, slot['radius'], stats)
            if not pieces:
                dropped[TOO_SMALL if small else INVALID] += 1
                continue
            label = (entry['names'][0] if entry['names'] else '') or entry['code'] or unnamed
            slot['groups'].setdefault(label, []).extend(pieces)
        return False

    @staticmethod
    def report(layer, dropped, stats, feedback):
        if stats['simplified']:
            feedback.pushInfo(tr(
                'Layer "{0}": {1} shapes simplified, tolerance up to {2} mm.').format(
                    layer.name(), stats['simplified'], number(stats['tolerance'], 3)))
        if stats['over']:
            feedback.pushWarning(tr(
                'Layer "{0}": {1} shapes still exceed the vertex limit.').format(
                    layer.name(), stats['over']))
        reasons = ', '.join('{0} {1}'.format(count, reason_label(key))
                            for key, count in dropped.items() if count)
        if reasons:
            feedback.pushInfo(tr('Layer "{0}": dropped {1}.').format(layer.name(), reasons))

    @staticmethod
    def group_element(identifier, label, attributes=''):
        return ['<g id="{0}" data-name="{1}"{2}>'.format(
            identifier, xml_text(label), (' ' + attributes) if attributes else ''),
            '<title>{0}</title>'.format(xml_text(label))]

    def layer_body(self, layer, classes, used, join_field, feedback):
        """SVG for one vector layer: class groups, named groups, loose shapes."""
        ordered = [slot for slot in sorted(classes.values(), key=lambda one: one['order'])
                   if slot['groups'] or slot['flat']]
        if not ordered:
            feedback.pushInfo(
                tr('Layer "{0}" has nothing inside the frame.').format(layer.name()))
            return []
        # A single unlabelled class is a single-symbol layer: no extra level.
        single = len(ordered) == 1 and not ordered[0]['label']
        body = self.group_element(xml_identifier(layer.name(), used), layer.name(),
                                  ordered[0]['attributes'] if single else '')
        for slot in ordered:
            if not single:
                body += self.group_element(
                    xml_identifier(slot['label'] or tr('class'), used),
                    slot['label'], slot['attributes'])
            for label in sorted(slot['groups'], key=lambda value: (value.casefold(), value)):
                body += self.group_element(xml_identifier(label, used), label)
                body += slot['groups'][label]
                body.append('</g>')
            body += slot['flat']
            if not single:
                body.append('</g>')
        body.append('</g>')
        named = sum(len(slot['groups']) for slot in ordered)
        grouped = tr(', grouped on {0}').format(join_field) if join_field else ''
        feedback.pushInfo(tr('Layer "{0}": {1} classes, {2} named groups{3}.').format(
            layer.name(), len(ordered), named, grouped))
        return body

    # ----------------------------------------------------------------- execution

    @staticmethod
    def document(frame, body):
        """The complete SVG document, page-sized and placed on the frame."""
        page_width, page_height = frame['page']
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" width="{0}mm" height="{1}mm" '
            'viewBox="0 0 {2} {3}">'.format(
                number(page_width, 3), number(page_height, 3),
                number(page_width, 3), number(page_height, 3)),
            '<style>path{fill-rule:evenodd}path,circle{stroke-linejoin:round}</style>',
            '<g id="carte" transform="{0}" data-map-rotation="{1}">'.format(
                frame['placement'], number(frame['map_rotation'], 6)),
        ]
        lines.extend(body)
        lines.append('</g>')
        lines.append('</svg>')
        return '\n'.join(lines) + '\n'

    def writer_for(self, parameters, context, frame):
        try:
            return FrameWriter(
                frame['corners'], frame['size'], frame['crs'],
                self.parameterAsInt(parameters, self.PRECISION, context),
                self.parameterAsBool(parameters, self.SPLIT_PARTS, context),
                self.parameterAsDouble(parameters, self.MIN_AREA, context),
                self.parameterAsInt(parameters, self.MAX_VERTICES, context))
        except ValueError:
            raise QgsProcessingException(tr('The map frame is degenerate.'))

    def processAlgorithm(self, parameters, context, feedback):
        layout = self.parameterAsLayout(parameters, self.LAYOUT, context)
        if layout is None:
            raise QgsProcessingException(tr('Select a print layout.'))
        item = self.parameterAsLayoutItem(parameters, self.MAP_ITEM, context, layout)
        if not isinstance(item, QgsLayoutItemMap):
            raise QgsProcessingException(tr('Select a map frame in that layout.'))
        destination = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        options = Options(
            use_style=self.parameterAsBool(parameters, self.STYLE, context),
            clip=self.parameterAsBool(parameters, self.CLIP, context),
            raster_dpi=self.parameterAsInt(parameters, self.RASTER_DPI, context),
            default_radius=self.parameterAsDouble(parameters, self.POINT_RADIUS, context))
        frame = self.frame_of(layout, item, feedback)
        writer = self.writer_for(parameters, context, frame)
        if writer.mask.isEmpty() or not writer.mask.isGeosValid():
            raise QgsProcessingException(tr('The map frame outline is invalid.'))
        layers = self.layers_of(parameters, context, item, feedback)
        naming = self.naming_of(parameters, context,
                                [one for one in layers if isinstance(one, QgsVectorLayer)])
        render_context = self.render_context_of(item, frame)

        used, body, canceled = set(), [], False
        for index, layer in enumerate(layers):
            if feedback.isCanceled():
                canceled = True
                break
            if isinstance(layer, QgsVectorLayer):
                fields = naming.get(layer.name().casefold(), ('', ''))
                classes, canceled = self.collect(layer, writer, fields, options,
                                                 render_context, context, feedback)
                body += self.layer_body(layer, classes, used, fields[1], feedback)
            else:
                element = self.image_element(layer, item, frame, options.raster_dpi,
                                             context, feedback)
                if element:
                    body += self.group_element(
                        xml_identifier(layer.name(), used), layer.name())
                    body.append(element)
                    body.append('</g>')
            feedback.setProgress(95 * (index + 1) / max(len(layers), 1))
            if canceled:
                break

        if not body:
            raise QgsProcessingException(tr('Nothing to export inside the map frame.'))
        with open(destination, 'w', encoding='utf-8') as handle:
            handle.write(self.document(frame, body))
        if canceled:
            feedback.pushWarning(tr(
                'Canceled: {0} is incomplete — check which layers it holds.').format(
                    destination))
        feedback.pushInfo(tr('Written to {0}.').format(destination))
        feedback.setProgress(100)
        return {self.OUTPUT: destination}
