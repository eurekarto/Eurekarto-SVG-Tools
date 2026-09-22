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
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCsException,
    QgsExpressionContext, QgsExpressionContextUtils, QgsFeatureRequest, QgsGeometry,
    QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemRegistry,
    QgsMapRendererParallelJob, QgsMapSettings,
    QgsPointXY,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterBoolean, QgsProcessingParameterDefinition,
    QgsProcessingParameterField, QgsProcessingParameterFileDestination,
    QgsProcessingParameterLayout, QgsProcessingParameterLayoutItem,
    QgsProcessingParameterMatrix, QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber, QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer, QgsRectangle, QgsRenderContext, QgsUnitTypes,
    QgsVariantUtils, QgsVectorLayer, QgsWkbTypes,
)

from .common import enum as _enum, number, tr, xml_text
from .layout_items import (DOTS_PER_MILLIMETRE, graft, marker_fragment,
                           painted_fragment, painted_labels)
from .scale_bar import ScaleBar, ellipsoid_of, latitudes_of


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
SYMBOL_FILL = _enum(Qgis, 'SymbolType', 'Fill')
SYMBOL_LINE = _enum(Qgis, 'SymbolType', 'Line')
SYMBOL_MARKER = _enum(Qgis, 'SymbolType', 'Marker')
NO_PEN = _enum(Qt, 'PenStyle', 'NoPen')
NO_BRUSH = _enum(Qt, 'BrushStyle', 'NoBrush')
WRITE_ONLY = _enum(QIODevice, 'OpenModeFlag', 'WriteOnly')
ADVANCED_PARAMETER = _enum(Qgis, 'ProcessingParameterFlag', 'Advanced',
                           QgsProcessingParameterDefinition, 'FlagAdvanced')

# Values that look like an ISO code but are "no data" markers. None of them is a
# valid ISO 3166 alpha-2 or alpha-3 code: 'NA' (Namibia) is deliberately absent.
PLACEHOLDER_IDS = frozenset({'-99', '-999', 'N/A', '#N/A', 'NULL', 'NONE', 'UNKNOWN'})

# Renderers that compute an image from the features rather than draw a symbol
# for each: there is nothing to group or name, so QGIS paints them as images.
IMAGE_RENDERERS = frozenset({'heatmapRenderer'})

# Largest image accepted, so a high DPI on a large page cannot exhaust memory.
MAXIMUM_PIXELS = 60000000
# Douglas-Peucker tolerances tried when a shape holds more vertices than the
# limit, in millimetres on the page. The ladder stops at the cap: beyond a few
# hundredths of a millimetre the simplification starts to show, and a visibly
# wrong coastline is worse than a path Illustrator may refuse to open.
FIRST_TOLERANCE = 0.01
DEFAULT_MAXIMUM_TOLERANCE = 0.1
# A shape no allowed tolerance can thin is cut into tiles that pave the same
# surface. Bounds on how many, so a pathological shape cannot explode the file.
MINIMUM_TILES, MAXIMUM_TILES = 2, 32

Options = namedtuple('Options', 'use_style clip raster_dpi default_radius')
ScaleOptions = namedtuple(
    'ScaleOptions', 'distance segments x y height font caption')

# Counting keys for dropped features; translated only when the log line is built.
OUTSIDE, REPROJECTION, INVALID, TOO_SMALL, UNSYMBOLIZED = (
    'outside', 'reprojection', 'invalid', 'small', 'symbology')


def reason_label(key):
    return {OUTSIDE: tr('outside the frame'),
            REPROJECTION: tr('reprojection failed'),
            INVALID: tr('unrepairable geometry'),
            TOO_SMALL: tr('below the minimum area'),
            UNSYMBOLIZED: tr('not drawn by the symbology')}[key]


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

    def __init__(self, corners, size, crs, precision, split_parts, min_area, max_vertices,
                 max_tolerance=DEFAULT_MAXIMUM_TOLERANCE):
        self.crs = crs
        self.precision = precision
        self.split_parts = split_parts
        self.min_area = min_area
        self.max_vertices = max_vertices
        self.max_tolerance = max_tolerance
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
    def signed_ring_area(points):
        """Ring area in square millimetres, negative when the ring winds the other way."""
        total = 0.0
        for index in range(len(points)):
            x1, y1 = points[index]
            x2, y2 = points[(index + 1) % len(points)]
            total += x1 * y2 - x2 * y1
        return total / 2.0

    @classmethod
    def ring_area(cls, points):
        """Ring area in square millimetres, points already in frame coordinates."""
        return abs(cls.signed_ring_area(points))

    @classmethod
    def oriented(cls, rings):
        """Rings wound so that holes cut and separate outlines add up.

        With fill-rule nonzero, a hole only cuts when it winds against its
        exterior, and two exteriors that overlap add up instead of cancelling
        each other — which is what repairing a self-intersecting ring produces.
        """
        if not rings:
            return rings
        exterior = rings[0]
        outward = cls.signed_ring_area(exterior) >= 0
        placed = [exterior if outward else exterior[::-1]]
        for hole in rings[1:]:
            inward = cls.signed_ring_area(hole) < 0
            placed.append(hole if inward else hole[::-1])
        return placed

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
        """Thin one shape until it is under the limit, or leave it untouched.

        The tolerance never passes max_tolerance: past that the simplification
        would be visible, and a dense path that Illustrator may refuse is a
        better outcome than a coastline cut into straight chords.
        """
        if not self.max_vertices or geometry_type == GEOMETRY_POINT:
            return geometry
        if self.vertex_count(geometry) <= self.max_vertices:
            return geometry
        tolerance = FIRST_TOLERANCE
        while tolerance <= self.max_tolerance * (1.0 + 1e-9):
            candidate = keep_type(geometry.simplify(tolerance * self.unit_mm), geometry_type)
            if candidate is not None and not candidate.isGeosValid():
                candidate = keep_type(candidate.makeValid(), geometry_type)
            if candidate is not None and self.vertex_count(candidate) <= self.max_vertices:
                stats['simplified'] += 1
                stats['tolerance'] = max(stats['tolerance'], tolerance)
                return candidate
            tolerance *= 2
        stats['over'] += 1
        return geometry

    @staticmethod
    def parts_of(geometry):
        """The geometry's parts, one by one; a single-part geometry yields itself."""
        return geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]

    @staticmethod
    def rings_of(part):
        """The rings of one single polygon: its exterior first, then its holes."""
        return part.asPolygon()

    def tiles_of(self, part, count):
        """The part cut into tiles, each holding a fraction of its vertices.

        Splitting keeps every vertex, where thinning would lose some: the tiles
        pave exactly the same surface.
        """
        side = int(math.ceil(math.sqrt(count / float(self.max_vertices))))
        side = max(MINIMUM_TILES, min(side + 1, MAXIMUM_TILES))
        box = part.boundingBox()
        width, height = box.width() / side, box.height() / side
        tiles = []
        for column in range(side):
            for row in range(side):
                left = box.xMinimum() + column * width
                bottom = box.yMinimum() + row * height
                rectangle = QgsRectangle(left, bottom, left + width, bottom + height)
                piece = keep_type(part.intersection(QgsGeometry.fromRect(rectangle)),
                                  GEOMETRY_POLYGON)
                if piece is not None:
                    tiles.append(piece)
        return tiles or [part]

    @staticmethod
    def chunks(points, size):
        """Consecutive runs of at most size points, each repeating the previous last.

        The repeat keeps the drawn line continuous across two paths.
        """
        if len(points) <= size:
            return [points]
        runs, start = [], 0
        while start < len(points) - 1:
            runs.append(points[start:start + size])
            start += size - 1
        return runs

    def outline_pieces(self, rings):
        """The rings as open polylines, short enough to survive an import."""
        pieces = []
        for ring in rings:
            closed = ring + [ring[0]] if ring and ring[0] != ring[-1] else ring
            for run in self.chunks(closed, self.max_vertices):
                drawn = self.path(run, False)
                if drawn:
                    pieces.append('<path fill="none" d="{0}"/>'.format(drawn))
        return pieces

    def dense_pieces(self, part, stats, stroke):
        """A shape too dense for one path: tiled fills, and its outline apart.

        The tiles carry no stroke, so the cuts between them never show; the
        original outline is drawn separately as open polylines.
        """
        stats['tiled'] += 1
        pieces, rings = [], []
        for tile in self.tiles_of(part, self.vertex_count(part)):
            for single in self.parts_of(tile):
                drawn = [one for one in
                         (self.path(ring, True) for ring in self.oriented(
                             [[self.to_frame(point) for point in ring]
                              for ring in self.rings_of(single)])) if one]
                if drawn:
                    pieces.append('<path stroke="none" d="{0}"/>'.format(''.join(drawn)))
        if stroke:
            rings = [[self.to_frame(point) for point in ring]
                     for ring in self.rings_of(part)]
            pieces.extend(self.outline_pieces(rings))
        return pieces

    def polygon_pieces(self, geometry, stats, stroke=True):
        """Path data per polygon part, each thinned on its own account.

        Parts are handled separately so that a dense mainland never costs an
        island its shape, and they are merged into one compound path only when
        the result still fits under the vertex limit. A part that no allowed
        tolerance can thin is tiled instead, which keeps every vertex.
        """
        drawn_parts, small, extra = [], 0, []
        for part in self.parts_of(geometry):
            before = stats['over']
            thinned = self.reduce_vertices(part, GEOMETRY_POLYGON, stats)
            if stats['over'] > before and self.max_vertices:
                extra.extend(self.dense_pieces(thinned, stats, stroke))
                continue
            # Thinning can hand back several polygons: simplifying a ring may make
            # it self-intersect, and the repair then splits it in two.
            for single in self.parts_of(thinned):
                rings = [[self.to_frame(point) for point in ring]
                         for ring in self.rings_of(single)]
                if not rings or self.ring_area(rings[0]) < self.min_area:
                    small += 1
                    continue
                rings = self.oriented(rings)
                drawn = [one for one in (self.path(ring, True) for ring in rings) if one]
                if drawn:
                    drawn_parts.append(''.join(drawn))
        if not self.split_parts and len(drawn_parts) > 1:
            merged = ''.join(drawn_parts)
            if not self.max_vertices or merged.count(',') <= self.max_vertices:
                drawn_parts = [merged]
            else:
                # Merging would push the compound path over the limit: the parts
                # stay separate rather than lose vertices to fit.
                stats['separated'] += 1
        return ['<path d="{0}"/>'.format(one) for one in drawn_parts] + extra, small

    def line_pieces(self, geometry):
        pieces = []
        for line in geometry.asMultiPolyline():
            drawn = self.path([self.to_frame(point) for point in line], False)
            if drawn:
                pieces.append('<path d="{0}"/>'.format(drawn))
        return pieces

    def point_pieces(self, geometry, radius, marker=None):
        """A copy of the class marker at each point, or a plain circle without one."""
        pieces = []
        for point in geometry.asMultiPoint():
            x, y = self.to_frame(point)
            if marker:
                pieces.append('<g transform="translate({0},{1}) scale({2})">{3}</g>'.format(
                    number(x, self.precision), number(y, self.precision),
                    number(1.0 / DOTS_PER_MILLIMETRE, 9), marker))
            else:
                pieces.append('<circle cx="{0}" cy="{1}" r="{2}"/>'.format(
                    number(x, self.precision), number(y, self.precision), number(radius, 3)))
        return pieces

    def pieces(self, geometry, geometry_type, radius, stats, stroke=True, marker=None):
        """SVG elements for one geometry, plus the parts below the minimum area."""
        if geometry_type == GEOMETRY_POLYGON:
            return self.polygon_pieces(geometry, stats, stroke)
        geometry = self.reduce_vertices(geometry, geometry_type, stats)
        geometry.convertToMultiType()
        if geometry_type == GEOMETRY_LINE:
            return self.line_pieces(geometry), 0
        return self.point_pieces(geometry, radius, marker), 0


def section(name, label):
    """Prefix a parameter label with its section.

    The Processing dialog has no section headers, so repeating the section name
    on each label is what visually groups the rows.
    """
    return '{0} · {1}'.format(name, label)


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
    SCALE_BAR = 'SCALE_BAR'
    SCALE_LATITUDES = 'SCALE_LATITUDES'
    SCALE_DISTANCE = 'SCALE_DISTANCE'
    SCALE_CAPTION = 'SCALE_CAPTION'
    SCALE_SEGMENTS = 'SCALE_SEGMENTS'
    SCALE_X = 'SCALE_X'
    SCALE_Y = 'SCALE_Y'
    SCALE_HEIGHT = 'SCALE_HEIGHT'
    SCALE_FONT = 'SCALE_FONT'
    SCALE_PROJECTION = 'SCALE_PROJECTION'
    SCALE_VISIBLE = 'SCALE_VISIBLE'
    MAX_TOLERANCE = 'MAX_TOLERANCE'
    LEGENDS = 'LEGENDS'
    LABELS = 'LABELS'
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
            'inside. Layers with no outline in QGIS get none here. Every level of a '
            'symbol is read — a polygon whose outline is a line level keeps it, and '
            'is not filled with its colour — but only as a flat fill and a stroke, '
            'so hatches, gradients and marker shapes come out plain, to restyle. '
            'Rasters are rendered by QGIS and embedded as images.</p>'
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
        card, layers, naming = tr('Map'), tr('Layers'), tr('Naming')
        look, shapes, bar, output = (tr('Appearance'), tr('Geometry'), tr('Scale bar'),
                                     tr('Output'))
        self.addParameter(QgsProcessingParameterLayout(
            self.LAYOUT, section(card, tr('Print layout'))))
        self.addParameter(QgsProcessingParameterLayoutItem(
            self.MAP_ITEM, section(card, tr('Map frame')),
            parentLayoutParameterName=self.LAYOUT, itemType=LAYOUT_MAP_ITEM))
        self.addParameter(QgsProcessingParameterBoolean(
            self.LABELS, section(card, tr('Include the labels')), defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.LEGENDS, section(card, tr('Include the layout legends')),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.LAYERS,
            section(layers, tr('Layers to export (empty = those shown in the frame)')),
            VECTOR_ANY_GEOMETRY, optional=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.GROUP_LAYER,
            section(naming, tr('Layer to split into named groups (e.g. countries)')),
            optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.GROUP_NAME_FIELD, section(naming, tr('Field holding the names')),
            parentLayerParameterName=self.GROUP_LAYER, optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.GROUP_JOIN_FIELD,
            section(naming, tr('Field grouping the polygons (e.g. ISO code)')),
            parentLayerParameterName=self.GROUP_LAYER, optional=True))
        self.addParameter(QgsProcessingParameterMatrix(
            self.NAMING,
            section(naming, tr('Other layers to name (layer, name field, grouping field)')),
            numberRows=1,
            headers=[tr('Layer'), tr('Name field'), tr('Grouping field')],
            defaultValue=['', '', ''], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.STYLE, section(look, tr('Keep the colours and classes from QGIS')),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.RASTERS, section(look, tr('Embed images (rasters)')), defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.RASTER_DPI, section(look, tr('Image resolution (DPI)')),
            PARAMETER_INTEGER, defaultValue=200, minValue=36, maxValue=1200))
        self.addParameter(QgsProcessingParameterBoolean(
            self.CLIP, section(shapes, tr('Cut at the frame edge')), defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_AREA, section(shapes, tr('Minimum polygon area (mm² on the page)')),
            PARAMETER_DOUBLE, defaultValue=0.05, minValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_VERTICES, section(shapes, tr('Maximum vertices per shape (0 = no limit)')),
            PARAMETER_INTEGER, defaultValue=10000, minValue=0, maxValue=10000000))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SCALE_BAR, section(bar, tr('Add a variable scale bar')), defaultValue=False))
        self.addParameter(QgsProcessingParameterString(
            self.SCALE_LATITUDES,
            section(bar, tr('Latitudes to show (degrees, comma separated)')),
            defaultValue='0, 30, 45, 60, 75'))
        self.addParameter(QgsProcessingParameterNumber(
            self.SCALE_DISTANCE,
            section(bar, tr('Distance per segment in kilometres (0 = automatic)')),
            PARAMETER_DOUBLE, defaultValue=0, minValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SCALE_VISIBLE, section(bar, tr('Only latitudes shown on the map')),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterString(
            self.SCALE_CAPTION, section(bar, tr('Scale bar caption')),
            defaultValue=tr('Distances along parallels'), optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SCALE_PROJECTION, section(bar, tr('Note the projection under the bar')),
            defaultValue=True))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, section(output, tr('SVG file')), fileFilter='SVG (*.svg)'))
        for parameter in (
                QgsProcessingParameterNumber(
                    self.PRECISION, section(shapes, tr('Coordinate precision (decimals)')),
                    PARAMETER_INTEGER, defaultValue=3, minValue=0, maxValue=9),
                QgsProcessingParameterNumber(
                    self.POINT_RADIUS, section(shapes, tr('Default point size (mm)')),
                    PARAMETER_DOUBLE, defaultValue=0.8, minValue=0.01),
                QgsProcessingParameterBoolean(
                    self.SPLIT_PARTS, section(shapes, tr('Separate islands into distinct paths')),
                    defaultValue=False),
                QgsProcessingParameterNumber(
                    self.MAX_TOLERANCE,
                    section(shapes, tr('Maximum simplification allowed (mm on the page)')),
                    PARAMETER_DOUBLE, defaultValue=DEFAULT_MAXIMUM_TOLERANCE, minValue=0.001,
                    maxValue=5.0),
                QgsProcessingParameterNumber(
                    self.SCALE_SEGMENTS, section(bar, tr('Number of segments')),
                    PARAMETER_INTEGER, defaultValue=2, minValue=1, maxValue=10),
                QgsProcessingParameterNumber(
                    self.SCALE_X,
                    section(bar, tr('Scale bar position from the left (mm, 0 = automatic)')),
                    PARAMETER_DOUBLE, defaultValue=0, minValue=0),
                QgsProcessingParameterNumber(
                    self.SCALE_Y,
                    section(bar, tr('Scale bar position from the top (mm, 0 = automatic)')),
                    PARAMETER_DOUBLE, defaultValue=0, minValue=0),
                QgsProcessingParameterNumber(
                    self.SCALE_HEIGHT, section(bar, tr('Bar height (mm)')),
                    PARAMETER_DOUBLE, defaultValue=2.0, minValue=0.2),
                QgsProcessingParameterNumber(
                    self.SCALE_FONT, section(bar, tr('Scale bar text size (mm)')),
                    PARAMETER_DOUBLE, defaultValue=2.5, minValue=0.5)):
            parameter.setFlags(parameter.flags() | ADVANCED_PARAMETER)
            self.addParameter(parameter)

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

    @staticmethod
    def default_style(geometry_type, radius):
        """Plain styling for a layer exported without its symbology."""
        if geometry_type == GEOMETRY_POLYGON:
            return 'fill="#cccccc" stroke="none"', radius
        if geometry_type == GEOMETRY_LINE:
            return 'fill="none" stroke="#000000" stroke-width="0.2"', radius
        return 'fill="#000000" stroke="none"', radius

    @staticmethod
    def symbol_layers(symbol):
        """Every level of a symbol, bottom to top, or an empty list."""
        try:
            return [symbol.symbolLayer(index) for index in range(symbol.symbolLayerCount())]
        except (AttributeError, TypeError):
            return []

    @staticmethod
    def layer_kind(symbol_layer):
        """Fill, line or marker — a fill symbol may well hold a line level.

        "Outline: simple line" is a line level sitting inside a polygon symbol;
        reading its colour as a fill is what paints a whole country black.
        """
        try:
            return symbol_layer.type()
        except (AttributeError, TypeError):
            if hasattr(symbol_layer, 'brushStyle'):
                return SYMBOL_FILL
            return SYMBOL_LINE if hasattr(symbol_layer, 'width') else SYMBOL_MARKER

    def line_of(self, symbol_layer):
        """Colour and width in millimetres of a line level."""
        if self.pen_is_none(symbol_layer):
            return None, None
        colour = symbol_layer.color() if hasattr(symbol_layer, 'color') else None
        width = None
        if hasattr(symbol_layer, 'width'):
            try:
                unit = getattr(symbol_layer, 'widthUnit', lambda: None)()
                width = self.render_millimetres(symbol_layer.width(), unit)
            except (AttributeError, TypeError):
                width = None
        return colour, width

    def outline_of(self, symbol_layer):
        """Outline colour and width of a fill or marker level, or (None, None)."""
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

    @classmethod
    def marker_radius(cls, symbol, default):
        """Half the marker size in millimetres, or the default when it has none."""
        try:
            size = cls.render_millimetres(symbol.size(), symbol.sizeUnit())
        except (AttributeError, TypeError):
            return default
        return size / 2.0 if size and size > 0 else default

    def read_symbol(self, symbol):
        """Fill colour, stroke colour and stroke width, read across every level.

        Levels are scanned rather than assumed: a polygon symbol can hold its
        outline as a line level, in either order, and the fill may sit above it.
        """
        fill, stroke, width = None, None, None
        for level in self.symbol_layers(symbol):
            kind = self.layer_kind(level)
            if kind == SYMBOL_LINE:
                if stroke is None:
                    stroke, width = self.line_of(level)
                continue
            if fill is None and not self.brush_is_none(level):
                fill = level.color() if hasattr(level, 'color') else None
            if stroke is None:
                stroke, width = self.outline_of(level)
        return fill, stroke, width

    def style_of(self, symbol, geometry_type, default_radius):
        """SVG presentation attributes and point radius read from a QGIS symbol."""
        radius = default_radius
        if symbol is None:
            return self.default_style(geometry_type, radius)
        try:
            opacity = float(symbol.opacity())
        except (AttributeError, TypeError, ValueError):
            opacity = 1.0
        fill, stroke, width = self.read_symbol(symbol)
        if geometry_type == GEOMETRY_LINE:
            colour = stroke if stroke is not None else fill
            if colour is None:
                colour = symbol.color()
            attributes = ['fill="none"'] + self.stroke_attributes(
                colour, width if width else 0.2)
            if opacity < 0.999:
                attributes.append('stroke-opacity="{0}"'.format(number(opacity, 3)))
            return ' '.join(attributes), radius
        if geometry_type == GEOMETRY_POINT:
            radius = self.marker_radius(symbol, radius)
            if fill is None:
                fill = symbol.color()
        fill_opacity = opacity * (fill.alphaF() if fill is not None else 0.0)
        attributes = (['fill="none"'] if fill is None
                      else self.fill_attributes(fill, fill_opacity, False))
        attributes += self.stroke_attributes(stroke, width)
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
            # Rules with a scale range are only active at the scale they cover.
            context.setRendererScale(item.scale())
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
        setter = getattr(settings, 'setTransformContext', None)
        if setter is not None:
            setter(context.transformContext())
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
        except QgsCsException:
            # The frame has no image in the layer CRS: drop the spatial filter and
            # read every feature rather than silently reading none.
            request.setFilterRect(QgsRectangle())
        return request, transform

    @classmethod
    def drawn_as_image(cls, layer):
        """True for a vector layer whose renderer paints an image, such as a heatmap."""
        return isinstance(layer, QgsVectorLayer) and cls.renderer_type(layer) in IMAGE_RENDERERS

    @staticmethod
    def renderer_type(layer):
        try:
            return layer.renderer().type()
        except (AttributeError, TypeError):
            return '?'

    @staticmethod
    def draws_nothing(layer):
        """True for a layer set to "No symbols": drawn for its labels alone."""
        renderer = layer.renderer()
        try:
            return renderer is not None and renderer.type() == 'nullSymbol'
        except (AttributeError, TypeError):
            return False

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
    def first_symbol(renderer, feature, render_context):
        """The symbol QGIS draws the feature with, whatever the renderer type.

        symbolForFeature is not implemented by the rule-based renderer, which
        always answers None; symbolsForFeature is implemented by every renderer,
        so it is asked first.
        """
        for reader in ('symbolsForFeature', 'originalSymbolsForFeature'):
            method = getattr(renderer, reader, None)
            if method is None:
                continue
            try:
                symbols = method(feature, render_context)
            except (AttributeError, TypeError):
                continue
            if symbols:
                return symbols[0]
        try:
            return renderer.symbolForFeature(feature, render_context)
        except (AttributeError, TypeError):
            return None

    @classmethod
    def class_of(cls, renderer, legend, feature, render_context):
        """(key, order, label, symbol); key None when the symbology draws nothing."""
        if renderer is None:
            return '', 0, '', None
        render_context.expressionContext().setFeature(feature)
        symbol = cls.first_symbol(renderer, feature, render_context)
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

    @staticmethod
    def marker_of(symbol, geometry_type, feedback):
        """The class marker drawn by QGIS, or None and a warning when it cannot be."""
        if symbol is None or geometry_type != GEOMETRY_POINT:
            return None
        try:
            return marker_fragment(symbol) or None
        except Exception as error:
            feedback.pushWarning(
                tr('A point symbol could not be drawn, circles are used instead: {0}')
                .format(error))
            return None

    def class_slot(self, classes, key, order, label, symbol, geometry_type, options,
                   invisible=False, feedback=None):
        """The slot collecting one symbology class, created with its style on first use.

        An invisible slot holds shapes QGIS does not draw but that must still be
        there to carry their names: no fill, no stroke, ready to be styled.
        """
        if key not in classes:
            attributes, radius = self.style_of(symbol, geometry_type, options.default_radius)
            if invisible:
                attributes = 'fill="none" stroke="none"'
            classes[key] = {'order': order, 'label': label, 'groups': {},
                            'attributes': attributes, 'radius': radius, 'flat': [],
                            'stroke': 'stroke="none"' not in attributes,
                            'marker': None if invisible or feedback is None
                            else self.marker_of(symbol, geometry_type, feedback)}
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

    @staticmethod
    def usable_join(layer, join_field, geometry_type, feedback):
        """The join field, or nothing when the layer holds no polygons to merge."""
        if join_field and geometry_type != GEOMETRY_POLYGON:
            feedback.pushWarning(
                tr('Layer "{0}" holds no polygons: grouping ignored.').format(layer.name()))
            return ''
        return join_field

    def explain(self, layer, classes, dropped, invisible, feedback):
        """Say why a layer came out empty or unstyled, rather than leave it to guesswork."""
        if invisible:
            feedback.pushInfo(tr(
                'Layer "{0}" is drawn without symbols: its shapes are written unstyled, '
                'to carry their names.').format(layer.name()))
        if not classes and dropped[UNSYMBOLIZED]:
            feedback.pushWarning(tr(
                'Layer "{0}": no feature matched its symbology ({1} renderer). Check its '
                'rules or categories.').format(layer.name(), self.renderer_type(layer)))

    def collect(self, layer, writer, fields, options, render_context, context, feedback):
        """Group one vector layer's features by symbology class, then by name."""
        name_field, join_field = fields
        geometry_type = layer.geometryType()
        join_field = self.usable_join(layer, join_field, geometry_type, feedback)
        invisible = options.use_style and self.draws_nothing(layer)
        if invisible and not (name_field or join_field):
            feedback.pushInfo(tr(
                'Layer "{0}" is drawn without symbols: only its labels are '
                'exported.').format(layer.name()))
            return {}, False
        renderer, legend = (None, {}) if invisible else self.renderer_of(
            layer, render_context, options.use_style)
        request, transform = self.request_for(layer, writer, context)
        classes, pending = {}, {}
        dropped = {OUTSIDE: 0, REPROJECTION: 0, INVALID: 0, TOO_SMALL: 0, UNSYMBOLIZED: 0}
        stats = {'simplified': 0, 'over': 0, 'separated': 0, 'tiled': 0, 'tolerance': 0.0}
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
                                       geometry_type, options, invisible, feedback)
                label = field_text(feature[name_field]) if name_field else ''
                if join_field:
                    self.hold_for_join(pending, key, geometry, label,
                                       field_text(feature[join_field]).upper())
                    continue
                pieces, small = writer.pieces(geometry, geometry_type, slot['radius'],
                                              stats, slot['stroke'], slot['marker'])
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
            self.stop_renderer(renderer, render_context, feedback)
        self.explain(layer, classes, dropped, invisible, feedback)
        self.report(layer, dropped, stats, feedback)
        return classes, canceled

    @staticmethod
    def stop_renderer(renderer, render_context, feedback):
        """Release the renderer, and report a refusal rather than hide it.

        This runs in a finally block, where an escaping exception would mask the
        one being handled.
        """
        if renderer is None:
            return
        try:
            renderer.stopRender(render_context)
        except Exception as error:
            feedback.pushInfo(tr('The symbology could not be released: {0}').format(error))

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
            pieces, small = writer.pieces(joined, geometry_type, slot['radius'], stats,
                                          slot['stroke'])
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
        if stats['separated']:
            feedback.pushInfo(tr(
                'Layer "{0}": {1} shapes kept as separate paths so that merging them '
                'would not exceed the vertex limit.').format(layer.name(), stats['separated']))
        if stats['tiled']:
            feedback.pushInfo(tr(
                'Layer "{0}": {1} shapes too dense for one path were cut into tiles that '
                'pave the same surface, with their outline drawn apart. No vertex was '
                'lost.').format(layer.name(), stats['tiled']))
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
    def document(frame, body, scale=(), style='', extras=(), labels=()):
        """The complete SVG document: the map group, then the scale bar beside it.

        The scale bar sits outside the map group on purpose: its coordinates are
        page millimetres, while the map group carries the frame's placement.
        """
        page_width, page_height = frame['page']
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" width="{0}mm" height="{1}mm" '
            'viewBox="0 0 {2} {3}">'.format(
                number(page_width, 3), number(page_height, 3),
                number(page_width, 3), number(page_height, 3)),
            '<style>{0}</style>'.format(style),
            # Presentation attributes rather than a stylesheet rule: Illustrator
            # only partly applies CSS on import, and both properties are
            # inherited, so declaring them once on the map group is enough.
            '<g id="carte" fill-rule="nonzero" stroke-linejoin="round" '
            'transform="{0}" data-map-rotation="{1}">'.format(
                frame['placement'], number(frame['map_rotation'], 6)),
        ]
        lines.extend(body)
        lines.append('</g>')
        lines.extend(labels)
        lines.extend(scale)
        lines.extend(extras)
        lines.append('</svg>')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def projection_name(crs):
        """The projection as a reader needs it: its name, then its code."""
        description = (crs.description() or '').strip()
        authid = (crs.authid() or '').strip()
        if description and authid:
            return '{0} ({1})'.format(description, authid)
        return description or authid or ''

    def labels_of(self, parameters, context, item, frame, used, feedback):
        """The labels of the map frame, placed by QGIS's own labelling engine."""
        if not self.parameterAsBool(parameters, self.LABELS, context):
            return []
        try:
            elements = painted_labels(item, frame['size'])
        except Exception as error:
            feedback.pushWarning(tr('The labels could not be rendered: {0}').format(error))
            return []
        if not elements:
            feedback.pushInfo(tr('No label is shown in the map frame.'))
            return []
        feedback.pushInfo(tr('Labels embedded, as text where the labelling allows it.'))
        return graft(xml_identifier('etiquettes', used), xml_text(tr('Labels')),
                     frame['placement'], elements)

    def legends_of(self, parameters, context, layout, item, used, feedback):
        """Every visible legend on the map frame's page, painted by QGIS itself."""
        if not self.parameterAsBool(parameters, self.LEGENDS, context):
            return []
        page_index = max(item.page(), 0)
        page = layout.pageCollection().page(page_index)
        legends = [one for one in layout.items()
                   if isinstance(one, QgsLayoutItemLegend) and one.isVisible()
                   and max(one.page(), 0) == page_index]
        if not legends:
            feedback.pushInfo(tr('No legend on the page of the map frame.'))
            return []
        factor = self.to_millimetres(layout, 1.0)
        blocks = []
        for legend in legends:
            # displayName() answers "<Legend>" for an item without an identifier.
            label = (legend.id() or '').strip() or tr('Legend')
            try:
                elements = painted_fragment(legend, factor)
            except Exception as error:
                feedback.pushWarning(tr('Legend "{0}" could not be rendered: {1}').format(
                    label, error))
                continue
            blocks += graft(xml_identifier('legende', used), xml_text(label),
                            self.placement_of(layout, legend, page), elements)
            feedback.pushInfo(tr('Legend "{0}" embedded as vectors.').format(label))
        return blocks

    def scale_bar_of(self, parameters, context, item, writer, frame, feedback):
        """The scale bar block and its style, or ([], '') when it is not wanted."""
        if not self.parameterAsBool(parameters, self.SCALE_BAR, context):
            return [], ''
        latitudes = latitudes_of(
            self.parameterAsString(parameters, self.SCALE_LATITUDES, context))
        if not latitudes:
            raise QgsProcessingException(
                tr('Give at least one latitude between -85 and 85.'))
        options = ScaleOptions(
            distance=self.parameterAsDouble(parameters, self.SCALE_DISTANCE, context),
            segments=self.parameterAsInt(parameters, self.SCALE_SEGMENTS, context),
            x=self.parameterAsDouble(parameters, self.SCALE_X, context),
            y=self.parameterAsDouble(parameters, self.SCALE_Y, context),
            height=self.parameterAsDouble(parameters, self.SCALE_HEIGHT, context),
            font=self.parameterAsDouble(parameters, self.SCALE_FONT, context),
            caption=self.parameterAsString(parameters, self.SCALE_CAPTION, context))
        wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        to_map = QgsCoordinateTransform(wgs84, frame['crs'], context.transformContext())
        try:
            longitude = QgsCoordinateTransform(
                frame['crs'], wgs84, context.transformContext()).transform(
                    item.extent().center()).x()
        except Exception:
            longitude = 0.0
        major, minor, name = ellipsoid_of(context.project(), frame['crs'], context)
        feedback.pushInfo(tr('Scale bar: centre longitude {0}°, measured on {1}.').format(
            number(longitude, 4), name))
        footer = [options.caption]
        if self.parameterAsBool(parameters, self.SCALE_PROJECTION, context):
            footer.append(self.projection_name(frame['crs']))
        bar = ScaleBar(options, (major, minor), longitude, to_map, writer, footer,
                       self.parameterAsBool(parameters, self.SCALE_VISIBLE, context))
        block = bar.build(frame['page'], latitudes, feedback)
        return block, bar.style(options.font) if block else ''

    def writer_for(self, parameters, context, frame):
        try:
            return FrameWriter(
                frame['corners'], frame['size'], frame['crs'],
                self.parameterAsInt(parameters, self.PRECISION, context),
                self.parameterAsBool(parameters, self.SPLIT_PARTS, context),
                self.parameterAsDouble(parameters, self.MIN_AREA, context),
                self.parameterAsInt(parameters, self.MAX_VERTICES, context),
                self.parameterAsDouble(parameters, self.MAX_TOLERANCE, context))
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
            if self.drawn_as_image(layer):
                feedback.pushInfo(tr(
                    'Layer "{0}" computes an image from its features ({1} renderer): '
                    'embedded as an image.').format(layer.name(), self.renderer_type(layer)))
            if isinstance(layer, QgsVectorLayer) and not self.drawn_as_image(layer):
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
        scale, scale_style = self.scale_bar_of(parameters, context, item, writer,
                                               frame, feedback)
        labels = self.labels_of(parameters, context, item, frame, used, feedback)
        legends = self.legends_of(parameters, context, layout, item, used, feedback)
        with open(destination, 'w', encoding='utf-8') as handle:
            handle.write(self.document(frame, body, scale, scale_style, legends, labels))
        if canceled:
            feedback.pushWarning(tr(
                'Canceled: {0} is incomplete — check which layers it holds.').format(
                    destination))
        feedback.pushInfo(tr('Written to {0}.').format(destination))
        feedback.setProgress(100)
        return {self.OUTPUT: destination}
