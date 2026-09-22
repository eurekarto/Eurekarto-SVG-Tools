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

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import PyQt5.QtCore as QtCore  # noqa: E402
import PyQt5.QtGui as QtGui  # noqa: E402
import PyQt5.QtSvg as QtSvg  # noqa: E402
import PyQt5.QtWidgets as QtWidgets  # noqa: E402

APPLICATION = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


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
        MapSettingsFlag=types.SimpleNamespace(DrawLabeling=1, SkipSymbolRendering=2,
                                              ForceVectorOutput=4),
        TextRenderFormat=types.SimpleNamespace(AlwaysText=1),
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
                 'QgsLayoutItemLegend', 'QgsMapRendererCustomPainterJob',
                 'QgsRenderContext', 'QgsVectorLayer'):
        setattr(core, name, type(name, (Exception,), {}))

    qgis.core = core
    qgis.PyQt = pyqt
    pyqt.QtCore = QtCore
    pyqt.QtGui = QtGui
    pyqt.QtSvg = QtSvg
    pyqt.QtWidgets = QtWidgets
    sys.modules.update({'qgis': qgis, 'qgis.core': core, 'qgis.PyQt': pyqt,
                        'qgis.PyQt.QtCore': QtCore, 'qgis.PyQt.QtGui': QtGui,
                        'qgis.PyQt.QtSvg': QtSvg, 'qgis.PyQt.QtWidgets': QtWidgets})

    package = types.ModuleType('eurekarto_svg_tools')
    package.__path__ = [str(pathlib.Path(__file__).resolve().parent / 'eurekarto_svg_tools')]
    sys.modules['eurekarto_svg_tools'] = package


install_stubs()
from eurekarto_svg_tools import layout_items  # noqa: E402
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


class Renderers(unittest.TestCase):
    """Every renderer type must yield the symbol QGIS actually draws."""

    symbol = object()

    def test_a_rule_based_renderer_answers_through_symbols_for_feature(self):
        # QgsRuleBasedRenderer.symbolForFeature always returns None.
        renderer = types.SimpleNamespace(
            symbolForFeature=lambda feature, context: None,
            symbolsForFeature=lambda feature, context: [self.symbol])
        self.assertIs(module.ExportLayoutSvg.first_symbol(renderer, None, None), self.symbol)

    def test_a_renderer_offering_only_the_single_form_still_works(self):
        renderer = types.SimpleNamespace(symbolForFeature=lambda feature, context: self.symbol)
        self.assertIs(module.ExportLayoutSvg.first_symbol(renderer, None, None), self.symbol)

    def test_a_feature_no_rule_matches_has_no_symbol(self):
        renderer = types.SimpleNamespace(
            symbolForFeature=lambda feature, context: None,
            symbolsForFeature=lambda feature, context: [],
            originalSymbolsForFeature=lambda feature, context: [])
        self.assertIsNone(module.ExportLayoutSvg.first_symbol(renderer, None, None))

    def test_a_layer_set_to_no_symbols_is_recognised(self):
        def layer(kind):
            return types.SimpleNamespace(renderer=lambda: types.SimpleNamespace(type=lambda: kind))
        self.assertTrue(module.ExportLayoutSvg.draws_nothing(layer('nullSymbol')))
        self.assertFalse(module.ExportLayoutSvg.draws_nothing(layer('RuleRenderer')))
        self.assertFalse(module.ExportLayoutSvg.draws_nothing(
            types.SimpleNamespace(renderer=lambda: None)))

    def test_a_layer_exported_without_its_symbology_gets_plain_styling(self):
        algorithm = module.ExportLayoutSvg.__new__(module.ExportLayoutSvg)
        for geometry_type in ('polygon', 'line', 'point'):
            attributes, radius = algorithm.style_of(None, geometry_type, 0.8)
            self.assertTrue(attributes)
            self.assertEqual(radius, 0.8)

    def test_an_invisible_class_carries_neither_fill_nor_stroke(self):
        algorithm = module.ExportLayoutSvg.__new__(module.ExportLayoutSvg)
        options = module.Options(use_style=True, clip=True, raster_dpi=200, default_radius=0.8)
        classes = {}
        slot = algorithm.class_slot(classes, '', 0, '', None, 'polygon', options, True)
        self.assertEqual(slot['attributes'], 'fill="none" stroke="none"')
        self.assertFalse(slot['stroke'])


class LabelTidying(unittest.TestCase):
    """What a renderer paints without showing anything must not reach the file."""

    WIDTH, HEIGHT = 3508, 2480

    def rendered(self, with_label_background=False):
        """A real Qt SVG, painted the way a map renderer paints a label pass."""
        buffer, generator = layout_items.svg_device(self.WIDTH, self.HEIGHT)
        painter = QtGui.QPainter(generator)
        painter.fillRect(QtCore.QRectF(0, 0, self.WIDTH, self.HEIGHT), QtGui.QColor(0, 0, 0, 0))
        for _ in range(3):  # one pass per layer, most with nothing to draw
            painter.save()
            painter.setPen(QtGui.QColor('#333333'))
            painter.restore()
        if with_label_background:
            painter.fillRect(QtCore.QRectF(480, 460, 200, 60), QtGui.QColor('#ffffff'))
        painter.save()
        painter.setPen(QtGui.QColor('#111111'))
        painter.drawText(QtCore.QPointF(500, 500), 'France')
        painter.restore()
        painter.end()
        return ''.join(layout_items.closed_content(buffer, canvas=(self.WIDTH, self.HEIGHT)))

    def test_the_canvas_sized_background_is_gone(self):
        self.assertNotIn('<rect', self.rendered())

    def test_no_empty_group_is_left(self):
        import re as regular
        self.assertIsNone(regular.search(r'<g\b[^>]*>\s*</g>', self.rendered()))

    def test_the_label_itself_is_kept(self):
        self.assertIn('France', self.rendered())

    def test_a_label_background_smaller_than_the_canvas_is_kept(self):
        self.assertIn('<rect', self.rendered(with_label_background=True))

    def test_nested_empty_groups_disappear_all_the_way_up(self):
        nested = '<g a="1"><g b="2"><g c="3"> </g></g></g><text>x</text>'
        self.assertEqual(layout_items.without_empty_groups(nested), '<text>x</text>')

    def test_transparent_sheets_go_whatever_their_size(self):
        # Three passes clearing with transparent rectangles, one of them inside a
        # scaled group so its width attribute no longer matches the canvas.
        buffer, generator = layout_items.svg_device(self.WIDTH, self.HEIGHT)
        painter = QtGui.QPainter(generator)
        for scale in (1.0, 0.5, 0.25):
            painter.save()
            painter.scale(scale, scale)
            painter.fillRect(QtCore.QRectF(0, 0, 1000, 700), QtGui.QColor(0, 0, 0, 0))
            painter.restore()
        painter.setPen(QtGui.QColor('#111111'))
        painter.drawText(QtCore.QPointF(500, 500), 'Bretagne')
        painter.end()
        content = ''.join(layout_items.closed_content(buffer, canvas=(self.WIDTH, self.HEIGHT)))
        self.assertNotIn('<rect', content)
        self.assertIn('Bretagne', content)

    def opaque_sheets(self, scales, label_background=None):
        """Opaque white sheets over the whole canvas, one per scaled pass, plus a label."""
        buffer, generator = layout_items.svg_device(self.WIDTH, self.HEIGHT)
        painter = QtGui.QPainter(generator)
        for scale in scales:
            painter.save()
            painter.scale(scale, scale)
            painter.fillRect(QtCore.QRectF(0, 0, self.WIDTH / scale, self.HEIGHT / scale),
                             QtGui.QColor('#ffffff'))
            painter.restore()
        if label_background is not None:
            painter.save()
            painter.scale(label_background, label_background)
            painter.fillRect(QtCore.QRectF(0, 0, 4000, 300), QtGui.QColor('#ffffff'))
            painter.restore()
        painter.setPen(QtGui.QColor('#111111'))
        painter.drawText(QtCore.QPointF(500, 500), 'Finistère')
        painter.end()
        return ''.join(layout_items.closed_content(buffer, canvas=(self.WIDTH, self.HEIGHT)))

    def test_opaque_sheets_go_whether_their_group_shrinks_or_enlarges_them(self):
        content = self.opaque_sheets((0.25, 1.0, 4.0))
        self.assertNotIn('<rect', content)
        self.assertIn('Finistère', content)

    def test_a_label_background_in_a_shrunk_group_is_kept(self):
        # 4000 px wide as written, 1000 px on the canvas: a label, not a sheet.
        content = self.opaque_sheets((1.0,), label_background=0.25)
        self.assertIn('<rect', content)

    def test_a_path_covering_the_canvas_goes_too(self):
        content = '<g fill="#ffffff" transform="matrix(1,0,0,1,0,0)"><path d="M0,0 L3508,0 ' \
                  'L3508,2480 L0,2480 Z"/></g><text>x</text>'
        self.assertNotIn('<path', layout_items.without_backgrounds(content, 3508, 2480))

    def test_the_group_scale_is_read_from_its_matrix(self):
        self.assertEqual(layout_items.group_scale('transform="matrix(0.25,0,0,4,0,0)"'),
                         (0.25, 4.0))
        self.assertEqual(layout_items.group_scale('fill="#fff"'), (1.0, 1.0))

    @staticmethod
    def embedded(image):
        import base64 as encoding
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        image.save(buffer, 'PNG')
        data = encoding.b64encode(bytes(buffer.data())).decode('ascii')
        return ('<g fill="none" transform="matrix(1,0,0,1,0,0)"><image x="0" y="0" '
                'width="350" height="248" preserveAspectRatio="none" '
                'xlink:href="data:image/png;base64,{0}"/></g>'.format(data))

    @staticmethod
    def canvas_image():
        image = QtGui.QImage(350, 248, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.transparent)
        return image

    def test_an_empty_intermediate_image_is_removed_with_its_group(self):
        # One per labelled layer: the case reported, canvas-sized and blank.
        content = self.embedded(self.canvas_image()) + '<text>Mali</text>'
        cleaned = layout_items.without_empty_groups(layout_items.without_blank_images(content))
        self.assertNotIn('<image', cleaned)
        self.assertNotIn('<g', cleaned)
        self.assertIn('Mali', cleaned)

    def test_an_image_showing_a_visible_pixel_is_kept(self):
        image = self.canvas_image()
        image.setPixelColor(10, 10, QtGui.QColor(0, 0, 0, 200))
        self.assertIn('<image', layout_items.without_blank_images(self.embedded(image)))

    def test_a_pixel_just_at_the_visibility_threshold_is_kept(self):
        image = self.canvas_image()
        image.setPixelColor(10, 10, QtGui.QColor(0, 0, 0, layout_items.VISIBLE_ALPHA))
        self.assertIn('<image', layout_items.without_blank_images(self.embedded(image)))

    def test_a_residue_nobody_can_see_is_removed(self):
        # The case reported: an image kept for a few near-transparent pixels.
        image = self.canvas_image()
        for x in range(0, 350, 7):
            image.setPixelColor(x, 120, QtGui.QColor(0, 0, 0, layout_items.VISIBLE_ALPHA - 1))
        self.assertNotIn('<image', layout_items.without_blank_images(self.embedded(image)))

    def test_a_faint_shadow_with_a_dense_core_is_kept(self):
        image = self.canvas_image()
        for x, alpha in ((20, 2), (21, 30), (22, 140), (23, 30), (24, 2)):
            image.setPixelColor(x, 50, QtGui.QColor(0, 0, 0, alpha))
        self.assertIn('<image', layout_items.without_blank_images(self.embedded(image)))

    @staticmethod
    def white_sheet(width=350, height=248):
        image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor('#ffffff'))
        return image

    def sized(self, image, width, height):
        return self.embedded(image).replace('width="350" height="248"',
                                             'width="{0}" height="{1}"'.format(width, height))

    def test_an_opaque_white_sheet_over_the_labels_canvas_is_removed(self):
        # The case reported: a layer QGIS flattened into a uniform white image.
        content = self.embedded(self.white_sheet()) + '<text>Niger</text>'
        cleaned = layout_items.without_blank_images(content, canvas=(350, 248))
        self.assertNotIn('<image', cleaned)
        self.assertIn('Niger', cleaned)

    def test_the_same_sheet_is_kept_outside_the_labels_render(self):
        # Without a canvas — a legend, say — a white image may be meant.
        content = self.embedded(self.white_sheet())
        self.assertIn('<image', layout_items.without_blank_images(content))

    def test_an_opaque_image_with_a_drawing_is_kept(self):
        image = self.white_sheet()
        image.setPixelColor(100, 100, QtGui.QColor('#222222'))
        cleaned = layout_items.without_blank_images(self.embedded(image), canvas=(350, 248))
        self.assertIn('<image', cleaned)

    def test_a_uniform_image_smaller_than_the_canvas_is_kept(self):
        content = self.sized(self.white_sheet(), 100, 60)
        self.assertIn('<image', layout_items.without_blank_images(content, canvas=(350, 248)))

    def test_uniformity_is_judged_on_every_pixel(self):
        pixels = b'\xff\xff\xff\xff' * 1000
        self.assertTrue(layout_items.uniform(pixels))
        self.assertFalse(layout_items.uniform(pixels[:-4] + b'\xfe\xff\xff\xff'))

    def test_an_undecodable_image_is_kept_rather_than_guessed_blank(self):
        content = ('<image x="0" y="0" width="1" height="1" '
                   'xlink:href="data:image/png;base64,not-base64!!"/>')
        self.assertEqual(layout_items.without_blank_images(content), content)

    def test_a_visible_shape_survives_even_when_it_is_large(self):
        buffer, generator = layout_items.svg_device(self.WIDTH, self.HEIGHT)
        painter = QtGui.QPainter(generator)
        painter.fillRect(QtCore.QRectF(0, 0, 1000, 700), QtGui.QColor('#88aacc'))
        painter.end()
        self.assertIn('<rect', ''.join(layout_items.closed_content(buffer)))

    def test_a_legend_background_is_never_mistaken_for_a_canvas(self):
        # The legend path does not ask for backgrounds to be dropped.
        buffer, generator = layout_items.svg_device(400, 200)
        painter = QtGui.QPainter(generator)
        painter.fillRect(QtCore.QRectF(0, 0, 400, 200), QtGui.QColor('#ffffff'))
        painter.end()
        self.assertIn('<rect', ''.join(layout_items.closed_content(buffer)))


class TextFormat(unittest.TestCase):
    """Legend text must come out as text, and the layout setting be left as found."""

    class Context:
        def __init__(self):
            self.format = 'outlines'
            self.during = None

        def textRenderFormat(self):
            return self.format

        def setTextRenderFormat(self, value):
            self.format = value

    def test_text_is_requested_as_text_while_painting(self):
        context = self.Context()
        with layout_items.text_kept_as_text(context):
            context.during = context.format
        self.assertEqual(context.during, layout_items.TEXT_AS_TEXT)

    def test_the_layout_setting_is_restored_afterwards(self):
        context = self.Context()
        with layout_items.text_kept_as_text(context):
            pass
        self.assertEqual(context.format, 'outlines')

    def test_restored_even_when_painting_fails(self):
        context = self.Context()
        with self.assertRaises(RuntimeError):
            with layout_items.text_kept_as_text(context):
                raise RuntimeError('paint failed')
        self.assertEqual(context.format, 'outlines')

    def test_a_context_without_the_setting_is_left_alone(self):
        with layout_items.text_kept_as_text(object()):
            pass


class PointMarkers(unittest.TestCase):
    point = Point(0, 0)

    def test_each_point_gets_a_copy_of_the_class_marker(self):
        geometry = types.SimpleNamespace(asMultiPoint=lambda: [self.point, self.point])
        pieces = writer().point_pieces(geometry, 0.8, '<path d="M0,0L1,1"/>')
        self.assertEqual(len(pieces), 2)
        self.assertTrue(all(piece.startswith('<g transform="translate(') for piece in pieces))
        self.assertTrue(all('<path d="M0,0L1,1"/>' in piece for piece in pieces))

    def test_without_a_marker_a_circle_is_written(self):
        geometry = types.SimpleNamespace(asMultiPoint=lambda: [self.point])
        pieces = writer().point_pieces(geometry, 0.8)
        self.assertTrue(pieces[0].startswith('<circle'))

    def test_a_heatmap_layer_is_drawn_as_an_image(self):
        class Layer(core_vector_layer()):
            def renderer(self):
                return types.SimpleNamespace(type=lambda: 'heatmapRenderer')

        self.assertTrue(module.ExportLayoutSvg.drawn_as_image(Layer()))

    def test_an_ordinary_layer_is_not(self):
        class Layer(core_vector_layer()):
            def renderer(self):
                return types.SimpleNamespace(type=lambda: 'RuleRenderer')

        self.assertFalse(module.ExportLayoutSvg.drawn_as_image(Layer()))


def core_vector_layer():
    return sys.modules['qgis.core'].QgsVectorLayer


class Legends(unittest.TestCase):
    """A legend is painted by the item itself into a real SVG generator."""

    class RenderContext:
        """As in QGIS: the preview flag can be read, not set from Python."""

        def isPreviewRender(self):
            return True

    class Item:
        """Paints a framed rectangle and a label, as a legend would."""

        def __init__(self):
            self.context = Legends.RenderContext()
            self.scale_seen = None

        def rect(self):
            return QtCore.QRectF(0, 0, 40, 20)

        def layout(self):
            return types.SimpleNamespace(renderContext=lambda: self.context)

        def paint(self, painter, option, widget):
            self.scale_seen = painter.worldTransform().m11()
            painter.setPen(QtGui.QPen(QtGui.QColor('#000000'), 0.2))
            painter.setBrush(QtGui.QColor('#ddeeff'))
            painter.drawRect(QtCore.QRectF(0, 0, 40, 20))
            painter.drawText(QtCore.QPointF(4, 12), 'Pays de la Loire & Bretagne')

    def painted(self):
        item = self.Item()
        return layout_items.painted_fragment(item, 1.0), item

    def test_paints_without_needing_to_change_the_render_mode(self):
        # QgsLayoutRenderContext has no public setIsPreviewRender: painting must
        # not depend on it.
        self.assertFalse(hasattr(self.RenderContext(), 'setIsPreviewRender'))
        elements, _ = self.painted()
        self.assertTrue(elements)

    def test_paints_at_print_resolution(self):
        _, item = self.painted()
        self.assertAlmostEqual(item.scale_seen, layout_items.DOTS_PER_MILLIMETRE, 6)

    def test_the_fragment_keeps_the_text_the_item_drew(self):
        elements, _ = self.painted()
        self.assertTrue(any('Pays de la Loire' in element for element in elements))

    def test_the_grafted_group_is_well_formed_and_placed(self):
        elements, _ = self.painted()
        group = layout_items.graft('legende', 'Legend', 'matrix(1,0,0,1,20,150)', elements)
        root = ElementTree.fromstring(''.join(group))
        self.assertEqual(root.get('id'), 'legende')
        self.assertIn('scale(', root.get('transform'))

    def test_the_slice_drops_the_generator_title_and_wrapper(self):
        data = (b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="1">'
                b'<title>Qt SVG Document</title><desc>Generated</desc>'
                b'<g fill="#fff"><rect width="2" height="2"/></g></svg>\n')
        content = ''.join(layout_items.fragment_content(data))
        self.assertIn('<rect', content)
        self.assertNotIn('<title>', content)
        self.assertNotIn('<desc>', content)
        self.assertNotIn('<svg', content)

    def test_a_document_that_is_not_svg_gives_nothing(self):
        self.assertEqual(layout_items.fragment_content(b'<html></html>'), [])

    def test_the_whole_document_stays_well_formed_with_a_legend(self):
        elements, _ = self.painted()
        legend = layout_items.graft('legende', 'Legend', 'matrix(1,0,0,1,20,150)', elements)
        frame = {'page': (297.0, 210.0), 'placement': 'matrix(1,0,0,1,0,0)',
                 'map_rotation': 0.0}
        ElementTree.fromstring(module.ExportLayoutSvg.document(frame, [], (), '', legend))

    def test_an_empty_fragment_writes_nothing(self):
        self.assertEqual(layout_items.graft('legende', 'Legend', 'matrix(1,0,0,1,0,0)', []), [])


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

    def test_labels_sit_just_above_the_map_and_under_the_rest(self):
        labels = ['<g id="etiquettes" transform="matrix(1,0,0,1,0,0) scale(0.1)">', '</g>']
        scale = ['<g id="echelle">', '</g>']
        legend = ['<g id="legende">', '</g>']
        text = module.ExportLayoutSvg.document(self.frame, self.body(), scale, '', legend,
                                               labels)
        root = ElementTree.fromstring(text)
        groups = [child.get('id') for child in root if child.tag.endswith('g')]
        self.assertEqual(groups, ['carte', 'etiquettes', 'echelle', 'legende'])

    def test_legends_sit_on_the_page_beside_the_map_and_the_scale_bar(self):
        scale = ['<g id="echelle">', '</g>']
        legend = ['<g id="legende" transform="matrix(1,0,0,1,0,0) scale(0.1)">', '</g>']
        text = module.ExportLayoutSvg.document(self.frame, self.body(), scale, '', legend)
        root = ElementTree.fromstring(text)
        groups = [child.get('id') for child in root if child.tag.endswith('g')]
        self.assertEqual(groups, ['carte', 'echelle', 'legende'])

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
