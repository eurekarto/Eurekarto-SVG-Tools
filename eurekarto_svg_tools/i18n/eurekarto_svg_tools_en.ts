<?xml version='1.0' encoding='utf-8'?>
<TS version="2.1" language="en" sourcelanguage="en">
  <context>
    <name>EurekartoSvgTools</name>
    <message>
      <source>, grouped on {0}</source>
      <translation>, grouped on {0}</translation>
    </message>
    <message>
      <source>&lt;p&gt;Writes a whole map frame to one SVG file: one group per layer, in map order, ready to open in Illustrator or Inkscape.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Named groups.&lt;/b&gt; Choose a layer and the field that names its features — each value becomes a named group, so countries arrive as "France", "Spain" and so on instead of anonymous paths. The grouping field (optional) merges the polygons sharing a value into a single shape: with an ISO code, a country and its islands become one object. Codes are compared without case or spaces, and no-data codes (-99, N/A, NULL) fall back to the name, so unrelated territories stay apart. Use the table below for further layers.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Colours.&lt;/b&gt; Fills, outlines and widths are read from the layer symbology, and each class of a categorized or graduated layer becomes its own group named after its legend label, with named features nested inside. Layers with no outline in QGIS get none here. Every level of a symbol is read — a polygon whose outline is a line level keeps it, and is not filled with its colour — but only as a flat fill and a stroke, so hatches, gradients and marker shapes come out plain, to restyle. Rasters are rendered by QGIS and embedded as images.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Alignment.&lt;/b&gt; The file is written in millimetres at the page size, with the map placed where the frame sits, so it can be pasted in place over the layout own SVG export — which carries the labels and the page furniture this algorithm does not export. Geometries are repaired and cut at the frame edge, so the file holds no clipping mask.&lt;/p&gt;&lt;p&gt;Shapes holding more vertices than the limit are simplified, because Illustrator does not open very dense paths. The log reports the alignment values it read, the classes and groups written, the shapes simplified and every feature dropped, by cause.&lt;/p&gt;</source>
      <translation>&lt;p&gt;Writes a whole map frame to one SVG file: one group per layer, in map order, ready to open in Illustrator or Inkscape.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Named groups.&lt;/b&gt; Choose a layer and the field that names its features — each value becomes a named group, so countries arrive as "France", "Spain" and so on instead of anonymous paths. The grouping field (optional) merges the polygons sharing a value into a single shape: with an ISO code, a country and its islands become one object. Codes are compared without case or spaces, and no-data codes (-99, N/A, NULL) fall back to the name, so unrelated territories stay apart. Use the table below for further layers.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Colours.&lt;/b&gt; Fills, outlines and widths are read from the layer symbology, and each class of a categorized or graduated layer becomes its own group named after its legend label, with named features nested inside. Layers with no outline in QGIS get none here. Every level of a symbol is read — a polygon whose outline is a line level keeps it, and is not filled with its colour — but only as a flat fill and a stroke, so hatches, gradients and marker shapes come out plain, to restyle. Rasters are rendered by QGIS and embedded as images.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Alignment.&lt;/b&gt; The file is written in millimetres at the page size, with the map placed where the frame sits, so it can be pasted in place over the layout own SVG export — which carries the labels and the page furniture this algorithm does not export. Geometries are repaired and cut at the frame edge, so the file holds no clipping mask.&lt;/p&gt;&lt;p&gt;Shapes holding more vertices than the limit are simplified, because Illustrator does not open very dense paths. The log reports the alignment values it read, the classes and groups written, the shapes simplified and every feature dropped, by cause.&lt;/p&gt;</translation>
    </message>
    <message>
      <source>A point symbol could not be drawn, circles are used instead: {0}</source>
      <translation>A point symbol could not be drawn, circles are used instead: {0}</translation>
    </message>
    <message>
      <source>About</source>
      <translation>About</translation>
    </message>
    <message>
      <source>Add a variable scale bar</source>
      <translation>Add a variable scale bar</translation>
    </message>
    <message>
      <source>Appearance</source>
      <translation>Appearance</translation>
    </message>
    <message>
      <source>Bar height (mm)</source>
      <translation>Bar height (mm)</translation>
    </message>
    <message>
      <source>Canceled: {0} is incomplete — check which layers it holds.</source>
      <translation>Canceled: {0} is incomplete — check which layers it holds.</translation>
    </message>
    <message>
      <source>Cartography for CAD</source>
      <translation>Cartography for CAD</translation>
    </message>
    <message>
      <source>Choose a name field, a grouping field, or both, for layer "{0}".</source>
      <translation>Choose a name field, a grouping field, or both, for layer "{0}".</translation>
    </message>
    <message>
      <source>Coordinate precision (decimals)</source>
      <translation>Coordinate precision (decimals)</translation>
    </message>
    <message>
      <source>Could not read the area shown by the map frame.</source>
      <translation>Could not read the area shown by the map frame.</translation>
    </message>
    <message>
      <source>Created by Blanche Lambert for Eurêkarto in 2026.</source>
      <translation>Created by Blanche Lambert for Eurêkarto in 2026.</translation>
    </message>
    <message>
      <source>Cut at the frame edge</source>
      <translation>Cut at the frame edge</translation>
    </message>
    <message>
      <source>Default point size (mm)</source>
      <translation>Default point size (mm)</translation>
    </message>
    <message>
      <source>Distance per segment in kilometres (0 = automatic)</source>
      <translation>Distance per segment in kilometres (0 = automatic)</translation>
    </message>
    <message>
      <source>Distances along parallels</source>
      <translation>Distances along parallels</translation>
    </message>
    <message>
      <source>Embed images (rasters)</source>
      <translation>Embed images (rasters)</translation>
    </message>
    <message>
      <source>Field grouping the polygons (e.g. ISO code)</source>
      <translation>Field grouping the polygons (e.g. ISO code)</translation>
    </message>
    <message>
      <source>Field holding the names</source>
      <translation>Field holding the names</translation>
    </message>
    <message>
      <source>Geometry</source>
      <translation>Geometry</translation>
    </message>
    <message>
      <source>Give at least one latitude between -85 and 85.</source>
      <translation>Give at least one latitude between -85 and 85.</translation>
    </message>
    <message>
      <source>Grouping field</source>
      <translation>Grouping field</translation>
    </message>
    <message>
      <source>Image resolution (DPI)</source>
      <translation>Image resolution (DPI)</translation>
    </message>
    <message>
      <source>Include the labels</source>
      <translation>Include the labels</translation>
    </message>
    <message>
      <source>Include the layout legends</source>
      <translation>Include the layout legends</translation>
    </message>
    <message>
      <source>Keep the colours and classes from QGIS</source>
      <translation>Keep the colours and classes from QGIS</translation>
    </message>
    <message>
      <source>Labels</source>
      <translation>Labels</translation>
    </message>
    <message>
      <source>Labels could not be split by layer ({0}); they are written together.</source>
      <translation>Labels could not be split by layer ({0}); they are written together.</translation>
    </message>
    <message>
      <source>Labels embedded for {0} layers, as text where the labelling allows it.</source>
      <translation>Labels embedded for {0} layers, as text where the labelling allows it.</translation>
    </message>
    <message>
      <source>Latitude {0}° is not on the map: no bar for it.</source>
      <translation>Latitude {0}° is not on the map: no bar for it.</translation>
    </message>
    <message>
      <source>Latitude {0}° skipped: {1}.</source>
      <translation>Latitude {0}° skipped: {1}.</translation>
    </message>
    <message>
      <source>Latitudes to show (degrees, comma separated)</source>
      <translation>Latitudes to show (degrees, comma separated)</translation>
    </message>
    <message>
      <source>Layer</source>
      <translation>Layer</translation>
    </message>
    <message>
      <source>Layer "{0}" computes an image from its features ({1} renderer): embedded as an image.</source>
      <translation>Layer "{0}" computes an image from its features ({1} renderer): embedded as an image.</translation>
    </message>
    <message>
      <source>Layer "{0}" embedded as an image, {1} x {2} px, {3} KB.</source>
      <translation>Layer "{0}" embedded as an image, {1} x {2} px, {3} KB.</translation>
    </message>
    <message>
      <source>Layer "{0}" has no field "{1}". Available fields: {2}.</source>
      <translation>Layer "{0}" has no field "{1}". Available fields: {2}.</translation>
    </message>
    <message>
      <source>Layer "{0}" has nothing inside the frame.</source>
      <translation>Layer "{0}" has nothing inside the frame.</translation>
    </message>
    <message>
      <source>Layer "{0}" holds no polygons: grouping ignored.</source>
      <translation>Layer "{0}" holds no polygons: grouping ignored.</translation>
    </message>
    <message>
      <source>Layer "{0}" is drawn without symbols: its shapes are written unstyled, to carry their names.</source>
      <translation>Layer "{0}" is drawn without symbols: its shapes are written unstyled, to carry their names.</translation>
    </message>
    <message>
      <source>Layer "{0}" is drawn without symbols: only its labels are exported.</source>
      <translation>Layer "{0}" is drawn without symbols: only its labels are exported.</translation>
    </message>
    <message>
      <source>Layer "{0}" is hidden at this scale.</source>
      <translation>Layer "{0}" is hidden at this scale.</translation>
    </message>
    <message>
      <source>Layer "{0}" is not a vector layer and was skipped.</source>
      <translation>Layer "{0}" is not a vector layer and was skipped.</translation>
    </message>
    <message>
      <source>Layer "{0}" is not among the exported layers. Available: {1}.</source>
      <translation>Layer "{0}" is not among the exported layers. Available: {1}.</translation>
    </message>
    <message>
      <source>Layer "{0}" produced no image.</source>
      <translation>Layer "{0}" produced no image.</translation>
    </message>
    <message>
      <source>Layer "{0}" would render as {1} x {2} pixels: lower the image resolution.</source>
      <translation>Layer "{0}" would render as {1} x {2} pixels: lower the image resolution.</translation>
    </message>
    <message>
      <source>Layer "{0}": could not encode the image.</source>
      <translation>Layer "{0}": could not encode the image.</translation>
    </message>
    <message>
      <source>Layer "{0}": dropped {1}.</source>
      <translation>Layer "{0}": dropped {1}.</translation>
    </message>
    <message>
      <source>Layer "{0}": no feature matched its symbology ({1} renderer). Check its rules or categories.</source>
      <translation>Layer "{0}": no feature matched its symbology ({1} renderer). Check its rules or categories.</translation>
    </message>
    <message>
      <source>Layer "{0}": value {1} covers several names ({2}); the first is used.</source>
      <translation>Layer "{0}": value {1} covers several names ({2}); the first is used.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} classes, {2} named groups{3}.</source>
      <translation>Layer "{0}": {1} classes, {2} named groups{3}.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} shapes kept as separate paths so that merging them would not exceed the vertex limit.</source>
      <translation>Layer "{0}": {1} shapes kept as separate paths so that merging them would not exceed the vertex limit.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} shapes simplified, tolerance up to {2} mm.</source>
      <translation>Layer "{0}": {1} shapes simplified, tolerance up to {2} mm.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} shapes too dense for one path were cut into tiles that pave the same surface, with their outline drawn apart. No vertex was lost.</source>
      <translation>Layer "{0}": {1} shapes too dense for one path were cut into tiles that pave the same surface, with their outline drawn apart. No vertex was lost.</translation>
    </message>
    <message>
      <source>Layer to split into named groups (e.g. countries)</source>
      <translation>Layer to split into named groups (e.g. countries)</translation>
    </message>
    <message>
      <source>Layers</source>
      <translation>Layers</translation>
    </message>
    <message>
      <source>Layers to export (empty = those shown in the frame)</source>
      <translation>Layers to export (empty = those shown in the frame)</translation>
    </message>
    <message>
      <source>Layout "{0}": page {1} x {2} mm, frame {3} x {4} mm, placement {5}, map rotation {6}°, scale 1:{7}, CRS {8}.</source>
      <translation>Layout "{0}": page {1} x {2} mm, frame {3} x {4} mm, placement {5}, map rotation {6}°, scale 1:{7}, CRS {8}.</translation>
    </message>
    <message>
      <source>Legend</source>
      <translation>Legend</translation>
    </message>
    <message>
      <source>Legend "{0}" could not be rendered: {1}</source>
      <translation>Legend "{0}" could not be rendered: {1}</translation>
    </message>
    <message>
      <source>Legend "{0}" embedded as vectors.</source>
      <translation>Legend "{0}" embedded as vectors.</translation>
    </message>
    <message>
      <source>Map</source>
      <translation>Map</translation>
    </message>
    <message>
      <source>Map frame</source>
      <translation>Map frame</translation>
    </message>
    <message>
      <source>Map to grouped SVG</source>
      <translation>Map to grouped SVG</translation>
    </message>
    <message>
      <source>Maximum simplification allowed (mm on the page)</source>
      <translation>Maximum simplification allowed (mm on the page)</translation>
    </message>
    <message>
      <source>Maximum vertices per shape (0 = no limit)</source>
      <translation>Maximum vertices per shape (0 = no limit)</translation>
    </message>
    <message>
      <source>Minimum polygon area (mm² on the page)</source>
      <translation>Minimum polygon area (mm² on the page)</translation>
    </message>
    <message>
      <source>Name field</source>
      <translation>Name field</translation>
    </message>
    <message>
      <source>Naming</source>
      <translation>Naming</translation>
    </message>
    <message>
      <source>No label is shown in the map frame.</source>
      <translation>No label is shown in the map frame.</translation>
    </message>
    <message>
      <source>No layer to export.</source>
      <translation>No layer to export.</translation>
    </message>
    <message>
      <source>No legend on the page of the map frame.</source>
      <translation>No legend on the page of the map frame.</translation>
    </message>
    <message>
      <source>No scale bar written: no latitude could be measured in this projection. First reason: {0}.</source>
      <translation>No scale bar written: no latitude could be measured in this projection. First reason: {0}.</translation>
    </message>
    <message>
      <source>Note the projection under the bar</source>
      <translation>Note the projection under the bar</translation>
    </message>
    <message>
      <source>Nothing to export inside the map frame.</source>
      <translation>Nothing to export inside the map frame.</translation>
    </message>
    <message>
      <source>Number of segments</source>
      <translation>Number of segments</translation>
    </message>
    <message>
      <source>Only latitudes shown on the map</source>
      <translation>Only latitudes shown on the map</translation>
    </message>
    <message>
      <source>Other layers to name (layer, name field, grouping field)</source>
      <translation>Other layers to name (layer, name field, grouping field)</translation>
    </message>
    <message>
      <source>Output</source>
      <translation>Output</translation>
    </message>
    <message>
      <source>Print layout</source>
      <translation>Print layout</translation>
    </message>
    <message>
      <source>SVG file</source>
      <translation>SVG file</translation>
    </message>
    <message>
      <source>Scale bar</source>
      <translation>Scale bar</translation>
    </message>
    <message>
      <source>Scale bar caption</source>
      <translation>Scale bar caption</translation>
    </message>
    <message>
      <source>Scale bar position from the left (mm, 0 = automatic)</source>
      <translation>Scale bar position from the left (mm, 0 = automatic)</translation>
    </message>
    <message>
      <source>Scale bar position from the top (mm, 0 = automatic)</source>
      <translation>Scale bar position from the top (mm, 0 = automatic)</translation>
    </message>
    <message>
      <source>Scale bar text size (mm)</source>
      <translation>Scale bar text size (mm)</translation>
    </message>
    <message>
      <source>Scale bar: centre longitude {0}°, measured on {1}.</source>
      <translation>Scale bar: centre longitude {0}°, measured on {1}.</translation>
    </message>
    <message>
      <source>Segment of {0} {1}: at {2}° it measures {3} mm on the page.</source>
      <translation>Segment of {0} {1}: at {2}° it measures {3} mm on the page.</translation>
    </message>
    <message>
      <source>Select a map frame in that layout.</source>
      <translation>Select a map frame in that layout.</translation>
    </message>
    <message>
      <source>Select a print layout.</source>
      <translation>Select a print layout.</translation>
    </message>
    <message>
      <source>Separate islands into distinct paths</source>
      <translation>Separate islands into distinct paths</translation>
    </message>
    <message>
      <source>The labels could not be rendered: {0}</source>
      <translation>The labels could not be rendered: {0}</translation>
    </message>
    <message>
      <source>The map frame has no coordinate reference system.</source>
      <translation>The map frame has no coordinate reference system.</translation>
    </message>
    <message>
      <source>The map frame has no size.</source>
      <translation>The map frame has no size.</translation>
    </message>
    <message>
      <source>The map frame is degenerate.</source>
      <translation>The map frame is degenerate.</translation>
    </message>
    <message>
      <source>The map frame is not on a page.</source>
      <translation>The map frame is not on a page.</translation>
    </message>
    <message>
      <source>The map frame outline is invalid.</source>
      <translation>The map frame outline is invalid.</translation>
    </message>
    <message>
      <source>The symbol of class "{0}" uses an effect QGIS can only draw as an image (a blend mode, a shadow, a shapeburst fill): it is embedded as one. Remove the effect for editable vectors.</source>
      <translation>The symbol of class "{0}" uses an effect QGIS can only draw as an image (a blend mode, a shadow, a shapeburst fill): it is embedded as one. Remove the effect for editable vectors.</translation>
    </message>
    <message>
      <source>The symbology could not be released: {0}</source>
      <translation>The symbology could not be released: {0}</translation>
    </message>
    <message>
      <source>Unnamed</source>
      <translation>Unnamed</translation>
    </message>
    <message>
      <source>Written to {0}.</source>
      <translation>Written to {0}.</translation>
    </message>
    <message>
      <source>below the minimum area</source>
      <translation>below the minimum area</translation>
    </message>
    <message>
      <source>class</source>
      <translation>class</translation>
    </message>
    <message>
      <source>default</source>
      <translation>default</translation>
    </message>
    <message>
      <source>measurement refused ({0})</source>
      <translation>measurement refused ({0})</translation>
    </message>
    <message>
      <source>none of the latitudes is on the map</source>
      <translation>none of the latitudes is on the map</translation>
    </message>
    <message>
      <source>not drawn by the symbology</source>
      <translation>not drawn by the symbology</translation>
    </message>
    <message>
      <source>outside the frame</source>
      <translation>outside the frame</translation>
    </message>
    <message>
      <source>reprojection failed</source>
      <translation>reprojection failed</translation>
    </message>
    <message>
      <source>the result has no length</source>
      <translation>the result has no length</translation>
    </message>
    <message>
      <source>the result, {0} mm, is far wider than the frame: the point falls outside what this projection can express</source>
      <translation>the result, {0} mm, is far wider than the frame: the point falls outside what this projection can express</translation>
    </message>
    <message>
      <source>the segment spans {0}° of longitude, more than the projection can show in one piece</source>
      <translation>the segment spans {0}° of longitude, more than the projection can show in one piece</translation>
    </message>
    <message>
      <source>unrepairable geometry</source>
      <translation>unrepairable geometry</translation>
    </message>
  </context>
</TS>
