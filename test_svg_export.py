"""Tests for eurekarto_svg_tools.svg_export, run without QGIS.

QGIS cannot be imported here, so the qgis package is replaced by the smallest
stand-ins the module actually touches. That covers the pure logic: coordinate
mapping, path writing, identifiers, vertex reduction, styling and the SVG
document. Anything that truly needs QGIS — renderers, feature iteration, raster
rendering — is out of reach and must be tested in QGIS.

Run: python3 test_svg_export.py
"""
import math
import pathlib
import sys
import types
import unittest
import xml.etree.ElementTree as ElementTree

import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui


# --------------------------------------------------------------------- stubs

class Point:
    def __init__(self, x, y):
        self._x, self._y = float(x), float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def __eq__(self, other):
        return (self._x, self._y) == (other.x(), other.y())


class Geometry:
    """Enough of QgsGeometry for the writer: vertex count and simplification."""

    def __init__(self, polygons):
        self.polygons = polygons

    def asMultiPolygon(self):
        return self.polygons

    def asMultiPolyline(self):
        return [ring for polygon in self.polygons for ring in polygon]

    def asMultiPoint(self):
        return [point for polygon in self.polygons for ring in polygon for point in ring]

    def asGeometryCollection(self):
        return [Geometry([polygon]) for polygon in self.polygons]

    def isMultipart(self):
        return len(self.polygons) > 1

    def asPolygon(self):
        # QGIS raises here rather than returning an empty list.
        if len(self.polygons) != 1:
            raise TypeError('MultiPolygon geometry cannot be converted to a polygon.')
        return self.polygons[0]

    def boundingBox(self):
        xs = [point.x() for polygon in self.polygons for ring in polygon for point in ring]
        ys = [point.y() for polygon in self.polygons for ring in polygon for point in ring]
        return types.SimpleNamespace(
            xMinimum=lambda: min(xs), yMinimum=lambda: min(ys),
            width=lambda: max(xs) - min(xs), height=lambda: max(ys) - min(ys))

    def intersection(self, other):
        left, bottom, right, top = other.box
        kept = []
        for polygon in self.polygons:
            inside = [point for point in polygon[0]
                      if left <= point.x() <= right and bottom <= point.y() <= top]
            if len(inside) >= 3:
                kept.append([inside])
        return Geometry(kept)

    def convertToMultiType(self):
        return True

    def isNull(self):
        return False

    def isEmpty(self):
        return not self.polygons

    def isGeosValid(self):
        return True

    def constGet(self):
        total = sum(len(ring) for polygon in self.polygons for ring in polygon)
        return types.SimpleNamespace(nCoordinates=lambda: total)

    def simplify(self, tolerance):
        """Crude but monotonic: keep one vertex out of every step."""
        step = max(int(tolerance * 100) + 1, 2)
        return Geometry([[ring[::step] + [ring[0]] for ring in polygon]
                         for polygon in self.polygons])

    def type(self):
        return 'polygon'

    def wkbType(self):
        return 'MultiPolygon'


def install_stubs():
    qgis = types.ModuleType('qgis')
    qgis.__path__ = []
    pyqt = types.ModuleType('qgis.PyQt')
    pyqt.__path__ = []
    core = types.ModuleType('qgis.core')

    class Enum:
        pass

    core.Qgis = types.SimpleNamespace(
        SymbolType=types.SimpleNamespace(Fill='fill', Line='line', Marker='marker'),
        GeometryType=types.SimpleNamespace(Polygon='polygon', Line='line', Point='point'),
        WkbType=types.SimpleNamespace(GeometryCollection='GeometryCollection'),
        LayoutUnit=types.SimpleNamespace(Millimeters='mm'),
        RenderUnit=types.SimpleNamespace(Millimeters='rmm', Points='rpt', Inches='rin',
                                         Pixels='rpx'),
        ProcessingSourceType=types.SimpleNamespace(VectorAnyGeometry='any'),
        GeometryOperationResult=types.SimpleNamespace(Success='success'),
        ProcessingAlgorithmFlag=types.SimpleNamespace(NoThreading=0))

    class QgsGeometry(Geometry):
        @staticmethod
        def fromPolygonXY(rings):
            return Geometry([rings])

        @staticmethod
        def collectGeometry(parts):
            return Geometry([polygon for part in parts for polygon in part.polygons])

    core.QgsGeometry = QgsGeometry
    core.QgsPointXY = Point
    core.QgsWkbTypes = types.SimpleNamespace(
        flatType=lambda value: value,
        PolygonGeometry='polygon', LineGeometry='line', PointGeometry='point',
        GeometryCollection='GeometryCollection')
    core.QgsRectangle = lambda *values: types.SimpleNamespace(values=values)
    QgsGeometry.fromRect = staticmethod(
        lambda rectangle: types.SimpleNamespace(box=rectangle.values))
    core.QgsUnitTypes = types.SimpleNamespace(
        LayoutMillimeters='mm', RenderMillimeters='rmm', RenderPoints='rpt',
        RenderInches='rin', RenderPixels='rpx')
    core.QgsVariantUtils = types.SimpleNamespace(isNull=lambda value: value is None)
    core.QgsProcessing = types.SimpleNamespace(TypeVectorAnyGeometry='any')
    core.QgsLayoutItemRegistry = types.SimpleNamespace(ItemType=types.SimpleNamespace(
        LayoutMap='map'))
    core.QgsProcessingParameterNumber = types.SimpleNamespace(
        Type=types.SimpleNamespace(Integer='int', Double='double'))
    core.QgsFeatureRequest = types.SimpleNamespace(
        InvalidGeometryCheck=types.SimpleNamespace(GeometryNoCheck='nocheck'))
    core.QgsCoordinateTransform = types.SimpleNamespace(
        TransformDirection=types.SimpleNamespace(ReverseTransform='reverse'))

    core.QgsCoordinateReferenceSystem = type('QgsCoordinateReferenceSystem',
                                             (Exception,), {})
    core.QgsCsException = type('QgsCsException', (Exception,), {})
    core.QgsDistanceArea = type('QgsDistanceArea', (Exception,), {})
    core.QgsProcessingParameterDefinition = types.SimpleNamespace(FlagAdvanced=1)
    core.Qgis.ProcessingParameterFlag = types.SimpleNamespace(Advanced=1)
    for name in ('QgsExpressionContext', 'QgsExpressionContextUtils', 'QgsLayoutItemMap',
                 'QgsMapRendererParallelJob', 'QgsMapSettings', 'QgsProcessingAlgorithm',
                 'QgsProcessingException', 'QgsProcessingParameterBoolean',
                 'QgsProcessingParameterField', 'QgsProcessingParameterFileDestination',
                 'QgsProcessingParameterLayout', 'QgsProcessingParameterLayoutItem',
                 'QgsProcessingParameterMatrix', 'QgsProcessingParameterMultipleLayers',
                 'QgsProcessingParameterString', 'QgsProcessingParameterVectorLayer',
                 'QgsRenderContext', 'QgsVectorLayer'):
        setattr(core, name, type(name, (Exception,), {}))

    qgis.core = core
    qgis.PyQt = pyqt
    pyqt.QtCore = QtCore
    pyqt.QtGui = QtGui
    sys.modules.update({'qgis': qgis, 'qgis.core': core, 'qgis.PyQt': pyqt,
                        'qgis.PyQt.QtCore': QtCore, 'qgis.PyQt.QtGui': QtGui})

    package = types.ModuleType('eurekarto_svg_tools')
    package.__path__ = [str(pathlib.Path(__file__).resolve().parent / 'eurekarto_svg_tools')]
    sys.modules['eurekarto_svg_tools'] = package


install_stubs()
from eurekarto_svg_tools import scale_bar  # noqa: E402
from eurekarto_svg_tools import svg_export as module  # noqa: E402


def rotated_frame(width_mm, height_mm, degrees, centre=(1000.0, 2000.0),
                  span=(4000.0, 3000.0)):
    """Frame corners in map coordinates: top-left, top-right, bottom-right, bottom-left."""
    angle = math.radians(degrees)
    half_x, half_y = span[0] / 2.0, span[1] / 2.0

    def turn(dx, dy):
        return (centre[0] + dx * math.cos(angle) - dy * math.sin(angle),
                centre[1] + dx * math.sin(angle) + dy * math.cos(angle))

    corners = [turn(-half_x, half_y), turn(half_x, half_y),
               turn(half_x, -half_y), turn(-half_x, -half_y)]
    return [Point(*corner) for corner in corners]


def writer(degrees=0.0, precision=3, split_parts=False, min_area=0.0, max_vertices=0):
    return module.FrameWriter(rotated_frame(200.0, 150.0, degrees), (200.0, 150.0),
                              'EPSG:3857', precision, split_parts, min_area, max_vertices)


# --------------------------------------------------------------------- tests

class EnumCompatibility(unittest.TestCase):
    def test_prefers_the_scoped_name(self):
        owner = types.SimpleNamespace(Scope=types.SimpleNamespace(Member='scoped'),
                                      Member='flat')
        self.assertEqual(module._enum(owner, 'Scope', 'Member'), 'scoped')

    def test_falls_back_to_flat_access(self):
        owner = types.SimpleNamespace(Member='flat')
        self.assertEqual(module._enum(owner, 'Scope', 'Member'), 'flat')

    def test_falls_back_to_the_legacy_owner(self):
        owner = types.SimpleNamespace()
        legacy = types.SimpleNamespace(OldName='legacy')
        self.assertEqual(module._enum(owner, 'Scope', 'New', legacy, 'OldName'), 'legacy')

    def test_reports_a_missing_member(self):
        with self.assertRaises(AttributeError):
            module._enum(types.SimpleNamespace(), 'Scope', 'Member')


class Numbers(unittest.TestCase):
    def test_trims_and_never_writes_negative_zero(self):
        self.assertEqual(module.number(1000.0, 3), '1000')
        self.assertEqual(module.number(123.4567, 2), '123.46')
        self.assertEqual(module.number(-0.0001, 3), '0')
        self.assertEqual(module.number(0.5, 0), '0')


class Identifiers(unittest.TestCase):
    def test_folds_accents_and_keeps_names_unique(self):
        used = set()
        self.assertEqual(module.xml_identifier("Côte d'Ivoire", used), 'Cote_d_Ivoire')
        self.assertEqual(module.xml_identifier("Côte d'Ivoire", used), 'Cote_d_Ivoire_2')

    def test_never_starts_with_a_digit(self):
        identifier = module.xml_identifier('-99', set())
        self.assertTrue(identifier[0].isalpha() or identifier[0] == '_')

    def test_survives_a_name_with_no_latin_characters(self):
        self.assertEqual(module.xml_identifier('中国', set()), 'groupe')

    def test_escapes_xml_text(self):
        self.assertEqual(module.xml_text('A & B <c> "d"'), 'A &amp; B &lt;c&gt; &quot;d&quot;')


class FrameMapping(unittest.TestCase):
    def test_corners_land_on_the_page_corners(self):
        for degrees in (0.0, 30.0, -17.5, 90.0):
            frame = writer(degrees)
            corners = rotated_frame(200.0, 150.0, degrees)
            places = 6
            self.assertAlmostEqual(frame.to_frame(corners[0])[0], 0.0, places)
            self.assertAlmostEqual(frame.to_frame(corners[0])[1], 0.0, places)
            self.assertAlmostEqual(frame.to_frame(corners[1])[0], 200.0, places)
            self.assertAlmostEqual(frame.to_frame(corners[3])[1], 150.0, places)

    def test_unit_is_map_units_per_millimetre(self):
        frame = writer(25.0)
        self.assertAlmostEqual(frame.unit_mm, math.sqrt((4000.0 / 200.0) * (3000.0 / 150.0)), 9)

    def test_ring_area_is_in_square_millimetres(self):
        square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
        self.assertAlmostEqual(module.FrameWriter.ring_area(square), 4.0, 9)


class Paths(unittest.TestCase):
    def test_drops_repeated_and_closing_vertices(self):
        frame = writer()
        points = [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)]
        self.assertEqual(frame.path(points, True), 'M0,0L10,0L10,10Z')

    def test_refuses_a_degenerate_ring(self):
        frame = writer()
        self.assertEqual(frame.path([(0.0, 0.0), (1.0, 1.0)], True), '')

    def test_open_path_has_no_closing_command(self):
        frame = writer()
        self.assertEqual(frame.path([(0.0, 0.0), (1.0, 1.0)], False), 'M0,0L1,1')


class VertexReduction(unittest.TestCase):
    @staticmethod
    def stats():
        return {'simplified': 0, 'over': 0, 'separated': 0, 'tolerance': 0.0}

    @staticmethod
    def dense(count):
        ring = [Point(i * 0.001, math.sin(i) * 0.5) for i in range(count)]
        return Geometry([[ring]])

    def test_leaves_a_light_shape_alone(self):
        frame = writer(max_vertices=10000)
        stats = self.stats()
        geometry = self.dense(500)
        self.assertIs(frame.reduce_vertices(geometry, 'polygon', stats), geometry)
        self.assertEqual(stats['simplified'], 0)

    def test_brings_a_dense_shape_under_the_limit(self):
        frame = writer(max_vertices=10000)
        stats = self.stats()
        reduced = frame.reduce_vertices(self.dense(40000), 'polygon', stats)
        self.assertLessEqual(frame.vertex_count(reduced), 10000)
        self.assertEqual(stats['simplified'], 1)
        self.assertGreater(stats['tolerance'], 0.0)

    def test_never_simplifies_beyond_the_allowed_tolerance(self):
        frame = writer(max_vertices=10000)
        frame.max_tolerance = 0.02
        stats = self.stats()
        reduced = frame.reduce_vertices(self.dense(40000), 'polygon', stats)
        self.assertLessEqual(stats['tolerance'], 0.02)
        self.assertTrue(stats['simplified'] or stats['over'])

    def test_leaves_a_shape_untouched_rather_than_deform_it(self):
        # A shape no allowed tolerance can thin must come back exactly as it was.
        frame = writer(max_vertices=10)
        frame.max_tolerance = 0.01
        stats = self.stats()
        original = self.dense(40000)
        reduced = frame.reduce_vertices(original, 'polygon', stats)
        self.assertIs(reduced, original)
        self.assertEqual(stats['over'], 1)
        self.assertEqual(stats['simplified'], 0)

    def test_thins_each_part_on_its_own_account(self):
        # A dense mainland beside a small island: the island keeps its vertices.
        mainland = [Point(index * 0.001, math.sin(index) * 0.5) for index in range(40000)]
        island = [Point(50, 50), Point(50.1, 50), Point(50.1, 50.1), Point(50, 50.1)]
        frame = writer(max_vertices=10000, min_area=0.0)
        stats = self.stats()
        pieces, _ = frame.polygon_pieces(Geometry([[mainland], [island]]), stats)
        subpaths = pieces[0].split('M')[1:] if len(pieces) == 1 else \
            [piece.split('M')[1] for piece in pieces]
        self.assertEqual(len(subpaths), 2)
        # The island is written whole: four corners, none lost to the mainland.
        self.assertEqual(subpaths[1].count(','), 4)

    def test_survives_a_part_that_repair_split_into_several_polygons(self):
        """simplify + makeValid can turn one polygon into a multipolygon."""
        class Splitting(Geometry):
            def simplify(self, tolerance):
                first = [Point(0, 0), Point(1, 0), Point(1, 1)]
                second = [Point(5, 5), Point(6, 5), Point(6, 6)]
                return Geometry([[first], [second]])

        dense = [Point(index * 0.001, math.sin(index)) for index in range(40000)]
        frame = writer(max_vertices=10, min_area=0.0)
        pieces, _ = frame.polygon_pieces(Splitting([[dense]]), self.stats())
        self.assertTrue(pieces)

    def test_keeps_parts_separate_when_merging_them_would_overflow(self):
        first = [Point(index * 0.001, math.sin(index) * 0.5) for index in range(9000)]
        second = [Point(50 + index * 0.001, math.cos(index) * 0.5) for index in range(9000)]
        frame = writer(max_vertices=10000, min_area=0.0)
        frame.max_tolerance = 0.0  # no thinning allowed at all
        stats = self.stats()
        pieces, _ = frame.polygon_pieces(Geometry([[first], [second]]), stats)
        self.assertEqual(len(pieces), 2)
        self.assertEqual(stats['separated'], 1)

    def test_disabled_when_the_limit_is_zero(self):
        frame = writer(max_vertices=0)
        stats = self.stats()
        geometry = self.dense(40000)
        self.assertIs(frame.reduce_vertices(geometry, 'polygon', stats), geometry)

    def test_counts_the_heaviest_part_when_islands_are_split(self):
        light, heavy = [Point(0, 0)] * 10, [Point(0, 0)] * 90
        geometry = Geometry([[light], [heavy]])
        self.assertEqual(writer(split_parts=False).vertex_count(geometry), 100)
        self.assertEqual(writer(split_parts=True).vertex_count(geometry), 90)


class DenseShapes(unittest.TestCase):
    """A shape no tolerance can thin is tiled, never left to be truncated."""

    @staticmethod
    def stats():
        return {'simplified': 0, 'over': 0, 'separated': 0, 'tiled': 0, 'tolerance': 0.0}

    @staticmethod
    def stubborn(count):
        """A shape no tolerance thins, laid out on a grid so tiles can bite."""
        class Stubborn(Geometry):
            def simplify(self, tolerance):
                return self

        return Stubborn([[[Point(index % 200, index // 200) for index in range(count)]]])

    def test_chunks_repeat_a_point_so_the_line_stays_continuous(self):
        runs = module.FrameWriter.chunks(list(range(10)), 4)
        self.assertEqual(runs[0][-1], runs[1][0])
        self.assertEqual(runs[-1][-1], 9)
        self.assertTrue(all(len(run) <= 4 for run in runs))

    def test_a_short_ring_is_left_in_one_run(self):
        self.assertEqual(module.FrameWriter.chunks([1, 2, 3], 10), [[1, 2, 3]])

    def test_an_untameable_shape_is_tiled_rather_than_written_whole(self):
        frame = writer(max_vertices=1000, min_area=0.0)
        stats = self.stats()
        pieces, _ = frame.polygon_pieces(self.stubborn(40000), stats, stroke=True)
        self.assertEqual(stats['tiled'], 1)
        self.assertGreater(len(pieces), 1)
        # Tiles carry the fill without a stroke, so their edges never show.
        self.assertTrue(any('stroke="none"' in piece for piece in pieces))
        # The outline is drawn apart, unfilled.
        self.assertTrue(any('fill="none"' in piece for piece in pieces))

    def test_no_outline_is_written_when_the_class_has_no_stroke(self):
        frame = writer(max_vertices=1000, min_area=0.0)
        pieces, _ = frame.polygon_pieces(self.stubborn(40000), self.stats(), stroke=False)
        self.assertFalse(any('fill="none"' in piece for piece in pieces))

    def test_every_written_path_stays_under_the_limit(self):
        frame = writer(max_vertices=1000, min_area=0.0)
        pieces, _ = frame.polygon_pieces(self.stubborn(40000), self.stats(), stroke=True)
        import re as regular
        for piece in pieces:
            data = regular.search(r'd="([^"]*)"', piece).group(1)
            self.assertLessEqual(data.count(','), 1000)


class RingOrientation(unittest.TestCase):
    """Holes must cut, and overlapping outlines must add up, under fill-rule nonzero."""

    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(2.0, 2.0), (4.0, 2.0), (4.0, 4.0), (2.0, 4.0)]

    def sign(self, ring):
        return module.FrameWriter.signed_ring_area(ring) >= 0

    def test_a_hole_is_turned_against_its_exterior(self):
        exterior, hole = module.FrameWriter.oriented([self.square, self.hole])
        self.assertNotEqual(self.sign(exterior), self.sign(hole))

    def test_a_hole_already_turned_the_right_way_is_left_alone(self):
        rings = module.FrameWriter.oriented([self.square, self.hole[::-1]])
        self.assertEqual(rings[1], self.hole[::-1])

    def test_two_separate_outlines_turn_the_same_way(self):
        first = module.FrameWriter.oriented([self.square])[0]
        second = module.FrameWriter.oriented([self.square[::-1]])[0]
        self.assertEqual(self.sign(first), self.sign(second))

    def test_area_stays_positive_whichever_way_a_ring_turns(self):
        self.assertAlmostEqual(module.FrameWriter.ring_area(self.square), 100.0, 9)
        self.assertAlmostEqual(module.FrameWriter.ring_area(self.square[::-1]), 100.0, 9)


class MinimumArea(unittest.TestCase):
    def test_drops_a_part_below_the_threshold(self):
        frame = writer(min_area=1.0)
        corners = rotated_frame(200.0, 150.0, 0.0)
        origin = corners[0]
        scale = 4000.0 / 200.0
        speck = [Point(origin.x() + 0.1 * scale, origin.y()),
                 Point(origin.x() + 0.2 * scale, origin.y()),
                 Point(origin.x() + 0.2 * scale, origin.y() - 0.1 * scale)]
        pieces, small = frame.polygon_pieces(
            Geometry([[speck]]), {'simplified': 0, 'over': 0, 'separated': 0, 'tolerance': 0.0})
        self.assertEqual(pieces, [])
        self.assertEqual(small, 1)


class JoinKeys(unittest.TestCase):
    def test_a_real_code_wins(self):
        self.assertEqual(module.ExportLayoutSvg.join_key('FRA', 'France'), ('code', 'FRA'))

    def test_a_placeholder_falls_back_to_the_name(self):
        self.assertEqual(module.ExportLayoutSvg.join_key('-99', 'Kosovo'), ('name', 'kosovo'))

    def test_two_placeholders_with_different_names_stay_apart(self):
        first = module.ExportLayoutSvg.join_key('-99', 'Kosovo')
        second = module.ExportLayoutSvg.join_key('-99', 'Somaliland')
        self.assertNotEqual(first, second)

    def test_namibia_is_not_treated_as_missing(self):
        self.assertEqual(module.ExportLayoutSvg.join_key('NA', 'Namibia'), ('code', 'NA'))


class Styles(unittest.TestCase):
    """Colours are read across every level of a symbol, whatever its type."""

    @staticmethod
    def fill_level(colour='#3366cc', stroke='#000000', width=0.26, pen=None, brush=None):
        level = types.SimpleNamespace(
            type=lambda: 'fill',
            color=lambda: QtGui.QColor(colour),
            strokeColor=lambda: QtGui.QColor(stroke),
            strokeWidth=lambda: width,
            strokeWidthUnit=lambda: 'rmm')
        if pen is not None:
            level.strokeStyle = lambda: pen
        if brush is not None:
            level.brushStyle = lambda: brush
        return level

    @staticmethod
    def line_level(colour='#0000ff', width=0.5, pen=None):
        level = types.SimpleNamespace(
            type=lambda: 'line',
            color=lambda: QtGui.QColor(colour),
            width=lambda: width,
            widthUnit=lambda: 'rmm')
        if pen is not None:
            level.penStyle = lambda: pen
        return level

    @staticmethod
    def marker_level(colour='#ff0000', size=3.0, stroke='#000000', width=0.2):
        return types.SimpleNamespace(
            type=lambda: 'marker',
            color=lambda: QtGui.QColor(colour),
            strokeColor=lambda: QtGui.QColor(stroke),
            strokeWidth=lambda: width,
            strokeWidthUnit=lambda: 'rmm',
            size=lambda: size,
            sizeUnit=lambda: 'rmm')

    @classmethod
    def symbol(cls, levels, opacity=1.0, colour='#3366cc'):
        return types.SimpleNamespace(
            color=lambda: QtGui.QColor(colour), opacity=lambda: opacity,
            symbolLayerCount=lambda: len(levels),
            symbolLayer=lambda index: levels[index],
            size=lambda: 3.0, sizeUnit=lambda: 'rmm')

    def setUp(self):
        self.algorithm = module.ExportLayoutSvg.__new__(module.ExportLayoutSvg)

    def style(self, levels, geometry_type='polygon', **kwargs):
        return self.algorithm.style_of(self.symbol(levels, **kwargs), geometry_type, 0.8)[0]

    def test_fills_a_polygon_and_keeps_its_outline(self):
        attributes = self.style([self.fill_level()])
        self.assertIn('fill="#3366cc"', attributes)
        self.assertIn('stroke="#000000"', attributes)
        self.assertIn('stroke-width="0.26"', attributes)

    def test_a_polygon_drawn_only_with_a_line_level_is_not_filled(self):
        # "Outline: simple line" is a line level inside a polygon symbol.
        attributes = self.style([self.line_level(colour='#112233', width=0.4)])
        self.assertIn('fill="none"', attributes)
        self.assertIn('stroke="#112233"', attributes)
        self.assertIn('stroke-width="0.4"', attributes)

    def test_a_line_level_below_a_fill_gives_the_outline_not_the_fill(self):
        attributes = self.style([self.line_level(colour='#112233'),
                                 self.fill_level(colour='#eeddcc')])
        self.assertIn('fill="#eeddcc"', attributes)
        self.assertIn('stroke="#112233"', attributes)

    def test_a_line_keeps_its_own_colour(self):
        for colour in ('#0000ff', '#ffffff'):
            attributes = self.style([self.line_level(colour=colour)], 'line')
            self.assertIn('stroke="{0}"'.format(colour), attributes)
            self.assertIn('fill="none"', attributes)

    def test_a_line_keeps_its_own_width(self):
        attributes = self.style([self.line_level(width=1.5)], 'line')
        self.assertIn('stroke-width="1.5"', attributes)

    def test_no_pen_means_no_stroke(self):
        attributes = self.style([self.fill_level(pen=QtCore.Qt.PenStyle.NoPen)])
        self.assertIn('stroke="none"', attributes)
        self.assertNotIn('stroke-width', attributes)

    def test_no_brush_means_no_fill(self):
        attributes = self.style([self.fill_level(brush=QtCore.Qt.BrushStyle.NoBrush)])
        self.assertIn('fill="none"', attributes)

    def test_zero_width_is_a_hairline_not_an_absence(self):
        attributes = self.style([self.fill_level(width=0.0)])
        self.assertIn('stroke="#000000"', attributes)
        self.assertIn('stroke-width="0.03"', attributes)

    def test_opacity_reaches_the_fill(self):
        attributes = self.style([self.fill_level()], opacity=0.5)
        self.assertIn('fill-opacity="0.5"', attributes)

    def test_a_marker_keeps_its_colour_and_its_size(self):
        symbol = self.symbol([self.marker_level(colour='#ff0000', size=3.0)])
        attributes, radius = self.algorithm.style_of(symbol, 'point', 0.8)
        self.assertIn('fill="#ff0000"', attributes)
        self.assertAlmostEqual(radius, 1.5, 9)

    def test_units_convert_to_millimetres(self):
        self.assertAlmostEqual(module.ExportLayoutSvg.render_millimetres(72.0, 'rpt'), 25.4, 9)
        self.assertAlmostEqual(module.ExportLayoutSvg.render_millimetres(1.0, 'rin'), 25.4, 9)
        self.assertIsNone(module.ExportLayoutSvg.render_millimetres(1.0, 'map units'))


class Document(unittest.TestCase):
    frame = {'page': (297.0, 210.0), 'placement': 'matrix(1,0,0,1,10,20)',
             'map_rotation': 0.0}

    def body(self):
        used = set()
        group = module.ExportLayoutSvg.group_element(
            module.xml_identifier('Pays & îles', used), 'Pays & îles', 'fill="#cccccc"')
        group.append('<path d="M0,0L1,0L1,1Z"/>')
        group.append('</g>')
        return group

    def test_the_document_is_well_formed_xml(self):
        text = module.ExportLayoutSvg.document(self.frame, self.body())
        root = ElementTree.fromstring(text)
        self.assertTrue(root.tag.endswith('svg'))

    def test_the_fill_rule_is_an_attribute_not_a_stylesheet_rule(self):
        root = ElementTree.fromstring(
            module.ExportLayoutSvg.document(self.frame, self.body()))
        carte = [child for child in root if child.get('id') == 'carte'][0]
        self.assertEqual(carte.get('fill-rule'), 'nonzero')

    def test_the_scale_bar_sits_beside_the_map_group_not_inside_it(self):
        scale = ['<g id="echelle">', '<rect x="10" y="10" width="20" height="2"/>', '</g>']
        text = module.ExportLayoutSvg.document(self.frame, self.body(), scale,
                                               '#echelle rect{stroke:#000000}')
        root = ElementTree.fromstring(text)
        groups = [child.get('id') for child in root
                  if child.tag.endswith('g')]
        self.assertEqual(groups, ['carte', 'echelle'])

    def test_page_size_is_in_millimetres_and_matches_the_view_box(self):
        text = module.ExportLayoutSvg.document(self.frame, self.body())
        root = ElementTree.fromstring(text)
        self.assertEqual(root.get('width'), '297mm')
        self.assertEqual(root.get('height'), '210mm')
        self.assertEqual(root.get('viewBox'), '0 0 297 210')

    def test_an_ampersand_in_a_layer_name_is_escaped(self):
        text = module.ExportLayoutSvg.document(self.frame, self.body())
        self.assertIn('data-name="Pays &amp; îles"', text)
        ElementTree.fromstring(text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
