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
    def dense(count):
        ring = [Point(i * 0.001, math.sin(i) * 0.5) for i in range(count)]
        return Geometry([[ring]])

    def test_leaves_a_light_shape_alone(self):
        frame = writer(max_vertices=10000)
        stats = {'simplified': 0, 'over': 0, 'tolerance': 0.0}
        geometry = self.dense(500)
        self.assertIs(frame.reduce_vertices(geometry, 'polygon', stats), geometry)
        self.assertEqual(stats['simplified'], 0)

    def test_brings_a_dense_shape_under_the_limit(self):
        frame = writer(max_vertices=10000)
        stats = {'simplified': 0, 'over': 0, 'tolerance': 0.0}
        reduced = frame.reduce_vertices(self.dense(40000), 'polygon', stats)
        self.assertLessEqual(frame.vertex_count(reduced), 10000)
        self.assertEqual(stats['simplified'], 1)
        self.assertGreater(stats['tolerance'], 0.0)

    def test_disabled_when_the_limit_is_zero(self):
        frame = writer(max_vertices=0)
        stats = {'simplified': 0, 'over': 0, 'tolerance': 0.0}
        geometry = self.dense(40000)
        self.assertIs(frame.reduce_vertices(geometry, 'polygon', stats), geometry)

    def test_counts_the_heaviest_part_when_islands_are_split(self):
        light, heavy = [Point(0, 0)] * 10, [Point(0, 0)] * 90
        geometry = Geometry([[light], [heavy]])
        self.assertEqual(writer(split_parts=False).vertex_count(geometry), 100)
        self.assertEqual(writer(split_parts=True).vertex_count(geometry), 90)


class MinimumArea(unittest.TestCase):
    def test_drops_a_part_below_the_threshold(self):
        frame = writer(min_area=1.0)
        corners = rotated_frame(200.0, 150.0, 0.0)
        origin = corners[0]
        scale = 4000.0 / 200.0
        speck = [Point(origin.x() + 0.1 * scale, origin.y()),
                 Point(origin.x() + 0.2 * scale, origin.y()),
                 Point(origin.x() + 0.2 * scale, origin.y() - 0.1 * scale)]
        pieces, small = frame.polygon_pieces(Geometry([[speck]]))
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
    @staticmethod
    def symbol(colour='#3366cc', opacity=1.0, pen=None, brush=None,
               stroke='#000000', width=0.26):
        layer = types.SimpleNamespace(
            strokeColor=lambda: QtGui.QColor(stroke),
            strokeWidth=lambda: width,
            strokeWidthUnit=lambda: 'rmm')
        if pen is not None:
            layer.strokeStyle = lambda: pen
        if brush is not None:
            layer.brushStyle = lambda: brush
        return types.SimpleNamespace(
            color=lambda: QtGui.QColor(colour), opacity=lambda: opacity,
            symbolLayerCount=lambda: 1, symbolLayer=lambda index: layer)

    def setUp(self):
        self.algorithm = module.ExportLayoutSvg.__new__(module.ExportLayoutSvg)

    def test_fills_a_polygon_and_keeps_its_outline(self):
        attributes, _ = self.algorithm.style_of(self.symbol(), 'polygon', 0.8)
        self.assertIn('fill="#3366cc"', attributes)
        self.assertIn('stroke="#000000"', attributes)
        self.assertIn('stroke-width="0.26"', attributes)

    def test_no_pen_means_no_stroke(self):
        symbol = self.symbol(pen=QtCore.Qt.PenStyle.NoPen)
        attributes, _ = self.algorithm.style_of(symbol, 'polygon', 0.8)
        self.assertIn('stroke="none"', attributes)
        self.assertNotIn('stroke-width', attributes)

    def test_no_brush_means_no_fill(self):
        symbol = self.symbol(brush=QtCore.Qt.BrushStyle.NoBrush)
        attributes, _ = self.algorithm.style_of(symbol, 'polygon', 0.8)
        self.assertIn('fill="none"', attributes)

    def test_zero_width_is_a_hairline_not_an_absence(self):
        attributes, _ = self.algorithm.style_of(self.symbol(width=0.0), 'polygon', 0.8)
        self.assertIn('stroke="#000000"', attributes)
        self.assertIn('stroke-width="0.03"', attributes)

    def test_opacity_reaches_the_fill(self):
        attributes, _ = self.algorithm.style_of(self.symbol(opacity=0.5), 'polygon', 0.8)
        self.assertIn('fill-opacity="0.5"', attributes)

    def test_units_convert_to_millimetres(self):
        self.assertAlmostEqual(module.ExportLayoutSvg.render_millimetres(72.0, 'rpt'), 25.4, 9)
        self.assertAlmostEqual(module.ExportLayoutSvg.render_millimetres(1.0, 'rin'), 25.4, 9)
        self.assertIsNone(module.ExportLayoutSvg.render_millimetres(1.0, 'map units'))


class ScaleBarMeasurement(unittest.TestCase):
    """The formula behind the variable bar, checked against geodetic references."""

    WGS84 = (6378137.0, 6356752.314245)

    def kilometres_per_degree(self, latitude, axes=None):
        major, minor = axes or self.WGS84
        return 1.0 / scale_bar.delta_longitude(1000.0, latitude, major, minor)

    def test_matches_the_published_length_of_a_degree(self):
        for latitude, expected in ((0, 111.320), (30, 96.486), (45, 78.847),
                                   (60, 55.800), (75, 28.902)):
            self.assertAlmostEqual(self.kilometres_per_degree(latitude), expected, 2)

    def test_works_on_a_sphere_where_the_axes_are_equal(self):
        self.assertAlmostEqual(
            self.kilometres_per_degree(0, (6371000.0, 6371000.0)), 111.195, 2)

    def test_refuses_a_pole_where_the_parallel_has_no_length(self):
        self.assertIsNone(scale_bar.delta_longitude(1000.0, 90.0, *self.WGS84))

    def test_rounds_the_automatic_distance_down_to_a_readable_value(self):
        self.assertEqual(scale_bar.nice_distance(8030000.0), 5000000.0)
        self.assertEqual(scale_bar.nice_distance(1234.0), 1000.0)
        self.assertEqual(scale_bar.nice_distance(260000.0), 250000.0)

    def test_labels_switch_to_metres_below_a_kilometre(self):
        self.assertEqual(scale_bar.distance_label(2500000.0), ('2500', 'km'))
        self.assertEqual(scale_bar.distance_label(500.0), ('500', 'm'))

    def test_reads_latitudes_and_drops_what_it_cannot_use(self):
        self.assertEqual(scale_bar.latitudes_of('0, 30; 45°, 60 , 95, oops, 45'),
                         [0.0, 30.0, 45.0, 60.0])
        self.assertEqual(scale_bar.latitudes_of('nothing here'), [])


class ScaleBarLayout(unittest.TestCase):
    """The caption and the projection line, and where they sit."""

    Options = __import__('collections').namedtuple(
        'Options', 'distance segments x y height font caption')

    def bar(self, footer):
        options = self.Options(distance=1000.0, segments=2, x=0.0, y=0.0, height=2.0,
                               font=2.5, caption='Distances along parallels')
        return scale_bar.ScaleBar(options, (6371000.0, 6371000.0), 0.0, None, None,
                                  footer)

    def test_keeps_the_lines_given_and_drops_the_empty_ones(self):
        self.assertEqual(self.bar(['Caption', '', None, 'Equal Earth (ESRI:53036)']).footer,
                         ['Caption', 'Equal Earth (ESRI:53036)'])

    def test_reserves_room_below_the_bars_for_every_line(self):
        one = self.bar(['Caption']).geometry_of((297.0, 210.0), 5)
        two = self.bar(['Caption', 'Equal Earth']).geometry_of((297.0, 210.0), 5)
        self.assertLess(two['top'], one['top'])
        self.assertAlmostEqual(one['top'] - two['top'], 2.5 * 1.3, 6)

    def test_names_the_projection_with_its_code(self):
        crs = types.SimpleNamespace(description=lambda: 'Sphere Equal Earth Greenwich',
                                    authid=lambda: 'ESRI:53036')
        self.assertEqual(module.ExportLayoutSvg.projection_name(crs),
                         'Sphere Equal Earth Greenwich (ESRI:53036)')

    def test_falls_back_to_whichever_part_exists(self):
        self.assertEqual(module.ExportLayoutSvg.projection_name(
            types.SimpleNamespace(description=lambda: '', authid=lambda: 'EPSG:4326')),
            'EPSG:4326')
        self.assertEqual(module.ExportLayoutSvg.projection_name(
            types.SimpleNamespace(description=lambda: '', authid=lambda: '')), '')


class VisibleLatitudes(unittest.TestCase):
    """Only the parallels the frame actually shows deserve a bar."""

    Options = __import__('collections').namedtuple(
        'Options', 'distance segments x y height font caption')

    class Frame:
        """A frame covering latitudes -60 to 60 at the measuring longitude."""

        def __init__(self):
            self.mask = types.SimpleNamespace(
                contains=lambda point: abs(point.y()) <= 60.0)
            self.extent = types.SimpleNamespace(
                contains=lambda point: abs(point.y()) <= 60.0)
            self.width = 200.0

    class Identity:
        @staticmethod
        def transform(point):
            return point

    def bar(self, only_visible=True):
        options = self.Options(distance=1000.0, segments=2, x=0.0, y=0.0, height=2.0,
                               font=2.5, caption='')
        return scale_bar.ScaleBar(options, (6371000.0, 6371000.0), 0.0, self.Identity(),
                                  self.Frame(), (), only_visible)

    def test_keeps_a_parallel_inside_the_frame(self):
        self.assertTrue(self.bar().on_the_map(45.0))

    def test_drops_a_parallel_the_map_does_not_show(self):
        self.assertFalse(self.bar().on_the_map(75.0))

    def test_keeps_everything_when_the_option_is_off(self):
        self.assertTrue(self.bar(only_visible=False).on_the_map(75.0))

    def test_reports_when_no_latitude_is_on_the_map(self):
        class Feedback:
            def __init__(self):
                self.lines = []

            def pushInfo(self, text):
                self.lines.append(text)

            def pushWarning(self, text):
                self.lines.append(text)

        feedback = Feedback()
        metres, lengths, reason = self.bar().measure([80.0, 85.0], feedback)
        self.assertEqual(lengths, [])
        self.assertIn('latitudes', reason)
        self.assertEqual(len(feedback.lines), 2)


class Sections(unittest.TestCase):
    def test_a_label_carries_its_section(self):
        self.assertEqual(module.section('Carte', 'Mise en page'), 'Carte · Mise en page')


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
