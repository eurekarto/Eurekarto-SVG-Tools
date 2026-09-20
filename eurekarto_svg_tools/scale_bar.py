# Copyright © 2026 Blanche Lambert / Eurêkarto
# SPDX-License-Identifier: GPL-2.0-or-later
"""Variable scale bar: one bar per latitude, drawn in page millimetres.

On a small-scale map the scale factor changes from place to place, so a single
bar cannot be right everywhere. Each bar shows the same real distance measured
along its own parallel, and their differing lengths are the message.

Distances are computed from the ellipsoid's radius of curvature in the prime
vertical rather than from QgsDistanceArea, which measures nothing at all when it
cannot resolve an ellipsoid name — a sphere-based projection is exactly the case
where that happens.
"""
import math

from qgis.core import QgsCoordinateReferenceSystem, QgsDistanceArea, QgsPointXY

from .common import number, tr, xml_text

# WGS84, used when neither the project nor the map CRS names a usable ellipsoid.
WGS84_SEMI_MAJOR = 6378137.0
WGS84_SEMI_MINOR = 6356752.314245

# Rounded segment lengths the automatic mode may choose, per decade.
NICE_STEPS = (1.0, 2.0, 2.5, 5.0)
# A bar wider than this share of the frame means the measurement ran off the
# projection rather than covering a genuinely long distance.
MAXIMUM_SHARE = 3.0
# Latitudes beyond this are refused: the parallels are too short to measure on.
MAXIMUM_LATITUDE = 85.0
# Share of the frame width the automatic distance aims for.
TARGET_SHARE = 0.4


def nice_distance(metres):
    """The nearest round distance at or below the requested one, 1/2/2.5/5 x 10^n."""
    if metres <= 0:
        return 1000.0
    decade = 10.0 ** math.floor(math.log10(metres))
    best = decade
    for step in NICE_STEPS:
        candidate = step * decade
        if candidate <= metres:
            best = candidate
    return best


def distance_label(metres):
    """A short label and its unit, in metres below a kilometre."""
    if metres >= 1000.0:
        return number(metres / 1000.0, 3), 'km'
    return number(metres, 1), 'm'


def latitudes_of(text):
    """Parse the latitude list, dropping anything out of range or unreadable."""
    values = []
    for piece in str(text).replace(';', ',').split(','):
        piece = piece.strip().replace('°', '')
        if not piece:
            continue
        try:
            value = float(piece.replace(',', '.'))
        except ValueError:
            continue
        if -MAXIMUM_LATITUDE <= value <= MAXIMUM_LATITUDE and value not in values:
            values.append(value)
    return values


def ellipsoid_of(project, crs, context):
    """Semi-axes to measure on, and the name to report.

    The project ellipsoid comes first, then the map CRS's own — a sphere-based
    projection measures on its sphere — then WGS84. A candidate counts only if
    setEllipsoid accepts it and real semi-axes come back: an unset
    QgsDistanceArea silently measures nothing.
    """
    measure = QgsDistanceArea()
    measure.setSourceCrs(QgsCoordinateReferenceSystem('EPSG:4326'),
                         context.transformContext())
    candidates = []
    if project is not None:
        candidates.append(project.ellipsoid())
    try:
        candidates.append(crs.ellipsoidAcronym())
    except (AttributeError, TypeError):
        pass
    candidates.append('WGS84')
    for candidate in candidates:
        if not candidate or candidate == 'NONE':
            continue
        try:
            if not measure.setEllipsoid(candidate):
                continue
        except (AttributeError, TypeError):
            continue
        major, minor = measure.ellipsoidSemiMajor(), measure.ellipsoidSemiMinor()
        if major and minor and major > 0 and minor > 0:
            return major, minor, candidate
    return WGS84_SEMI_MAJOR, WGS84_SEMI_MINOR, 'WGS84'


def delta_longitude(distance, latitude, major, minor):
    """Degrees of longitude covering that distance along the parallel.

    distance = N(lat) cos(lat) dlambda, with N the radius of curvature in the
    prime vertical: exact on an ellipsoid, and on a sphere where the semi-axes
    are equal.
    """
    eccentricity = 1.0 - (minor * minor) / (major * major)
    phi = math.radians(latitude)
    curvature = major / math.sqrt(1.0 - eccentricity * math.sin(phi) ** 2)
    along = curvature * math.cos(phi)
    # At a pole the cosine is not exactly zero in floating point, so a plain
    # positivity test would return an astronomical angle instead of refusing.
    if along <= major * 1e-9:
        return None
    return math.degrees(distance / along)


class ScaleBar:
    """Builds the SVG of a variable scale bar, in page millimetres."""

    def __init__(self, options, ellipsoid, longitude, transform, writer, footer=(),
                 only_visible=True):
        self.options = options
        self.ellipsoid = ellipsoid
        self.longitude = longitude
        self.transform = transform
        self.writer = writer
        self.only_visible = only_visible
        # Caption, then the projection name: one line each, under the bars.
        self.footer = [line for line in footer if line]

    def page_length(self, latitude, metres):
        """Millimetres on the page for a real distance along that parallel.

        Returns (length, None) or (None, reason): a refused measurement must say
        what refused it, otherwise every projection failure looks the same.
        """
        delta = delta_longitude(metres, latitude, self.ellipsoid[0], self.ellipsoid[1])
        if delta is None:
            return None, tr('the result has no length')
        if abs(delta) >= 180.0:
            return None, tr('the segment spans {0}° of longitude, more than the '
                            'projection can show in one piece').format(number(abs(delta), 1))
        try:
            start = QgsPointXY(self.longitude, latitude)
            end = QgsPointXY(self.longitude + delta, latitude)
            first = self.writer.to_frame(self.transform.transform(start))
            second = self.writer.to_frame(self.transform.transform(end))
        except Exception as error:
            return None, tr('measurement refused ({0})').format(error)
        length = math.hypot(second[0] - first[0], second[1] - first[1])
        if not math.isfinite(length) or length <= 0:
            return None, tr('the result has no length')
        if length > self.writer.width * MAXIMUM_SHARE:
            return None, tr('the result, {0} mm, is far wider than the frame: the point '
                            'falls outside what this projection can express').format(
                                number(length, 1))
        return length, None

    def on_the_map(self, latitude):
        """Whether that parallel crosses the frame at the measuring longitude.

        A bar for a latitude the map does not show states a scale the reader
        cannot check, so it is dropped rather than drawn.
        """
        if not self.only_visible:
            return True
        try:
            point = self.transform.transform(QgsPointXY(self.longitude, latitude))
        except Exception:
            return False
        try:
            if self.writer.mask.contains(point):
                return True
        except (AttributeError, TypeError):
            pass
        return bool(self.writer.extent.contains(point))

    def measure(self, latitudes, feedback):
        """Segment distance in metres and the page length of each bar."""
        shown = []
        for latitude in latitudes:
            if self.on_the_map(latitude):
                shown.append(latitude)
            else:
                feedback.pushInfo(tr('Latitude {0}° is not on the map: no bar for it.')
                                  .format(number(latitude, 3)))
        if not shown:
            return None, [], tr('none of the latitudes is on the map')
        latitudes = shown
        metres = self.options.distance * 1000.0
        segments = self.options.segments
        if metres <= 0:
            probe, reason = self.page_length(latitudes[0], 1000000.0)
            if not probe:
                return None, [], reason
            target = self.writer.width * TARGET_SHARE / segments
            metres = nice_distance(1000000.0 * target / probe)
        lengths, first_reason = [], None
        for latitude in latitudes:
            length, reason = self.page_length(latitude, metres)
            if length is None:
                first_reason = first_reason or reason
                feedback.pushWarning(
                    tr('Latitude {0}° skipped: {1}.').format(number(latitude, 3), reason))
                continue
            lengths.append((latitude, length * segments))
        return metres, lengths, first_reason

    def geometry_of(self, page, rows):
        """Where the block sits and how its rows are spaced, in page millimetres."""
        font, height = self.options.font, self.options.height
        gap = font * 0.4
        block = rows * (height + gap)
        left = self.options.x if self.options.x > 0 else 15.0 + font * 2.5
        footer = len(self.footer) * font * 1.3
        top = (self.options.y if self.options.y > 0
               else page[1] - 15.0 - block - footer)
        return {'left': left, 'top': top, 'height': height, 'gap': gap, 'font': font,
                'footer_y': top + block + font * 0.9}

    @staticmethod
    def identifier(latitude):
        return 'latitude_' + number(latitude, 3).replace('-', 'S').replace('.', '_')

    def bar_row(self, index, latitude, length, geometry):
        """One latitude: alternating segments, its outline, and its latitude label."""
        segments = self.options.segments
        height, font = geometry['height'], geometry['font']
        top = geometry['top'] + index * (height + geometry['gap'])
        left = geometry['left']
        step = length / segments
        parts = ['<g id="{0}" data-name="{1}°">'.format(
            self.identifier(latitude), number(latitude, 3))]
        for segment in range(segments):
            parts.append(
                '<rect x="{0}" y="{1}" width="{2}" height="{3}" fill="{4}"/>'.format(
                    number(left + segment * step, 3), number(top, 3), number(step, 3),
                    number(height, 3), '#000000' if segment % 2 == 0 else '#ffffff'))
        parts.append('<rect x="{0}" y="{1}" width="{2}" height="{3}" fill="none"/>'.format(
            number(left, 3), number(top, 3), number(length, 3), number(height, 3)))
        parts.append('<text x="{0}" y="{1}" text-anchor="end">{2}°</text>'.format(
            number(left - font * 0.6, 3), number(top + height - font * 0.15, 3),
            number(latitude, 3)))
        parts.append('</g>')
        return parts

    def tick_labels(self, length, metres, geometry):
        """Distance labels above the first bar: 0, one segment, two segments…"""
        segments = self.options.segments
        left, font = geometry['left'], geometry['font']
        baseline = geometry['top'] - font * 0.5
        _, unit = distance_label(metres * segments)
        parts = ['<g id="graduations">']
        for segment in range(segments + 1):
            value, _ = distance_label(metres * segment)
            text = value if segment < segments else '{0} {1}'.format(value, unit)
            parts.append('<text x="{0}" y="{1}" text-anchor="middle">{2}</text>'.format(
                number(left + segment * length / segments, 3), number(baseline, 3),
                xml_text(text)))
        parts.append('</g>')
        return parts

    def build(self, page, latitudes, feedback):
        """The <g id="echelle"> block, or an empty list with the reason logged."""
        metres, lengths, reason = self.measure(latitudes, feedback)
        if not lengths:
            feedback.pushWarning(tr(
                'No scale bar written: no latitude could be measured in this '
                'projection. First reason: {0}.').format(reason))
            return []
        value, unit = distance_label(metres)
        for latitude, length in lengths:
            feedback.pushInfo(tr('Segment of {0} {1}: at {2}° it measures {3} mm on '
                                 'the page.').format(value, unit, number(latitude, 3),
                                                     number(length / self.options.segments, 2)))
        geometry = self.geometry_of(page, len(lengths))
        block = ['<g id="echelle">']
        block.extend(self.tick_labels(lengths[0][1], metres, geometry))
        for index, (latitude, length) in enumerate(lengths):
            block.extend(self.bar_row(index, latitude, length, geometry))
        for index, line in enumerate(self.footer):
            block.append('<text id="{0}" x="{1}" y="{2}">{3}</text>'.format(
                'legende' if index == 0 else 'legende_{0}'.format(index + 1),
                number(geometry['left'], 3),
                number(geometry['footer_y'] + index * geometry['font'] * 1.3, 3),
                xml_text(line)))
        block.append('</g>')
        return block

    @staticmethod
    def style(font):
        return ('#echelle rect{{stroke:#000000;stroke-width:0.15}}'
                '#echelle text{{font-family:sans-serif;font-size:{0}px;'
                'fill:#000000}}').format(number(font, 3))
