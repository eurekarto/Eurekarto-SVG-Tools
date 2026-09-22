<?xml version='1.0' encoding='utf-8'?>
<TS version="2.1" language="fr" sourcelanguage="en">
  <context>
    <name>EurekartoSvgTools</name>
    <message>
      <source>, grouped on {0}</source>
      <translation>, regroupées sur {0}</translation>
    </message>
    <message>
      <source>&lt;p&gt;Writes a whole map frame to one SVG file: one group per layer, in map order, ready to open in Illustrator or Inkscape.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Named groups.&lt;/b&gt; Choose a layer and the field that names its features — each value becomes a named group, so countries arrive as "France", "Spain" and so on instead of anonymous paths. The grouping field (optional) merges the polygons sharing a value into a single shape: with an ISO code, a country and its islands become one object. Codes are compared without case or spaces, and no-data codes (-99, N/A, NULL) fall back to the name, so unrelated territories stay apart. Use the table below for further layers.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Colours.&lt;/b&gt; Fills, outlines and widths are read from the layer symbology, and each class of a categorized or graduated layer becomes its own group named after its legend label, with named features nested inside. Layers with no outline in QGIS get none here. Every level of a symbol is read — a polygon whose outline is a line level keeps it, and is not filled with its colour — but only as a flat fill and a stroke, so hatches, gradients and marker shapes come out plain, to restyle. Rasters are rendered by QGIS and embedded as images.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Alignment.&lt;/b&gt; The file is written in millimetres at the page size, with the map placed where the frame sits, so it can be pasted in place over the layout own SVG export — which carries the labels and the page furniture this algorithm does not export. Geometries are repaired and cut at the frame edge, so the file holds no clipping mask.&lt;/p&gt;&lt;p&gt;Shapes holding more vertices than the limit are simplified, because Illustrator does not open very dense paths. The log reports the alignment values it read, the classes and groups written, the shapes simplified and every feature dropped, by cause.&lt;/p&gt;</source>
      <translation>&lt;p&gt;Écrit tout un cadre de carte dans un seul fichier SVG : un groupe par couche, dans l’ordre de la carte, prêt à ouvrir dans Illustrator ou Inkscape.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Groupes nommés.&lt;/b&gt; Choisissez une couche et le champ qui nomme ses entités : chaque valeur devient un groupe portant ce nom, et les pays arrivent en « France », « Espagne » plutôt qu’en tracés anonymes. Le champ de regroupement (facultatif) réunit en une seule forme les polygones qui partagent une valeur : avec un code ISO, un pays et ses îles ne font plus qu’un objet. Les codes sont comparés sans tenir compte de la casse ni des espaces, et les codes sans valeur (-99, N/A, NULL) retombent sur le nom, pour que des territoires sans rapport ne soient pas réunis. Le tableau en dessous sert aux autres couches.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Couleurs.&lt;/b&gt; Remplissages, contours et épaisseurs sont lus dans la symbologie, et chaque classe d’une couche catégorisée ou graduée forme son propre groupe, nommé d’après son libellé de légende, avec les entités nommées à l’intérieur. Une couche sans contour dans QGIS n’en a pas non plus ici. Tous les niveaux d’un symbole sont lus — un polygone dont le contour est un niveau de ligne le garde, au lieu d’être rempli de sa couleur — mais le rendu reste un aplat et un trait : hachures, dégradés et formes de marqueurs ressortent simplifiés, à rhabiller. Les rasters sont dessinés par QGIS et intégrés en images.&lt;/p&gt;&lt;p&gt;&lt;b&gt;Calage.&lt;/b&gt; Le fichier est écrit en millimètres à la taille de la page, la carte placée là où se trouve le cadre : il se colle sur place par-dessus l’export SVG de la mise en page, qui porte les étiquettes et l’habillage que cet algorithme n’exporte pas. Les géométries sont réparées et coupées au bord du cadre, donc le fichier ne contient aucun masque d’écrêtage.&lt;/p&gt;&lt;p&gt;Les formes qui comptent plus de sommets que la limite sont simplifiées, parce qu’Illustrator n’ouvre pas les tracés très denses. Le journal indique les valeurs de calage lues, les classes et groupes écrits, les formes simplifiées et chaque entité écartée, avec sa raison.&lt;/p&gt;</translation>
    </message>
    <message>
      <source>A point symbol could not be drawn, circles are used instead: {0}</source>
      <translation>Un symbole de point n’a pas pu être dessiné, des cercles le remplacent : {0}</translation>
    </message>
    <message>
      <source>About</source>
      <translation>À propos</translation>
    </message>
    <message>
      <source>Add a variable scale bar</source>
      <translation>Ajouter une barre d’échelle variable</translation>
    </message>
    <message>
      <source>Appearance</source>
      <translation>Apparence</translation>
    </message>
    <message>
      <source>Bar height (mm)</source>
      <translation>Hauteur des barres (mm)</translation>
    </message>
    <message>
      <source>Canceled: {0} is incomplete — check which layers it holds.</source>
      <translation>Annulé : {0} est incomplet — vérifiez les couches qu’il contient.</translation>
    </message>
    <message>
      <source>Cartography for CAD</source>
      <translation>Cartographie pour DAO</translation>
    </message>
    <message>
      <source>Choose a name field, a grouping field, or both, for layer "{0}".</source>
      <translation>Choisissez un champ nom, un champ de regroupement, ou les deux, pour la couche « {0} ».</translation>
    </message>
    <message>
      <source>Coordinate precision (decimals)</source>
      <translation>Précision des coordonnées (décimales)</translation>
    </message>
    <message>
      <source>Could not read the area shown by the map frame.</source>
      <translation>Impossible de lire la zone affichée par le cadre de carte.</translation>
    </message>
    <message>
      <source>Created by Blanche Lambert for Eurêkarto in 2026.</source>
      <translation>Créé par Blanche Lambert pour Eurêkarto en 2026.</translation>
    </message>
    <message>
      <source>Cut at the frame edge</source>
      <translation>Couper au bord du cadre</translation>
    </message>
    <message>
      <source>Default point size (mm)</source>
      <translation>Taille des points par défaut (mm)</translation>
    </message>
    <message>
      <source>Distance per segment in kilometres (0 = automatic)</source>
      <translation>Distance par segment en kilomètres (0 = automatique)</translation>
    </message>
    <message>
      <source>Distances along parallels</source>
      <translation>Distances le long des parallèles</translation>
    </message>
    <message>
      <source>Embed images (rasters)</source>
      <translation>Intégrer les images (rasters)</translation>
    </message>
    <message>
      <source>Field grouping the polygons (e.g. ISO code)</source>
      <translation>Champ qui regroupe les polygones (ex. code ISO)</translation>
    </message>
    <message>
      <source>Field holding the names</source>
      <translation>Champ qui porte les noms</translation>
    </message>
    <message>
      <source>Geometry</source>
      <translation>Géométrie</translation>
    </message>
    <message>
      <source>Give at least one latitude between -85 and 85.</source>
      <translation>Donnez au moins une latitude comprise entre -85 et 85.</translation>
    </message>
    <message>
      <source>Grouping field</source>
      <translation>Champ de regroupement</translation>
    </message>
    <message>
      <source>Image resolution (DPI)</source>
      <translation>Résolution des images (DPI)</translation>
    </message>
    <message>
      <source>Include the labels</source>
      <translation>Inclure les étiquettes</translation>
    </message>
    <message>
      <source>Include the layout legends</source>
      <translation>Inclure les légendes de la mise en page</translation>
    </message>
    <message>
      <source>Keep the colours and classes from QGIS</source>
      <translation>Garder les couleurs et les classes de QGIS</translation>
    </message>
    <message>
      <source>Labels</source>
      <translation>Étiquettes</translation>
    </message>
    <message>
      <source>Labels embedded, as text where the labelling allows it.</source>
      <translation>Étiquettes intégrées, en texte lorsque l’étiquetage le permet.</translation>
    </message>
    <message>
      <source>Latitude {0}° is not on the map: no bar for it.</source>
      <translation>La latitude {0}° n’est pas sur la carte : pas de barre pour elle.</translation>
    </message>
    <message>
      <source>Latitude {0}° skipped: {1}.</source>
      <translation>Latitude {0}° ignorée : {1}.</translation>
    </message>
    <message>
      <source>Latitudes to show (degrees, comma separated)</source>
      <translation>Latitudes à représenter (degrés, séparées par des virgules)</translation>
    </message>
    <message>
      <source>Layer</source>
      <translation>Couche</translation>
    </message>
    <message>
      <source>Layer "{0}" computes an image from its features ({1} renderer): embedded as an image.</source>
      <translation>La couche « {0} » calcule une image à partir de ses entités (rendu {1}) : intégrée en image.</translation>
    </message>
    <message>
      <source>Layer "{0}" embedded as an image, {1} x {2} px, {3} KB.</source>
      <translation>Couche « {0} » intégrée en image, {1} x {2} px, {3} Ko.</translation>
    </message>
    <message>
      <source>Layer "{0}" has no field "{1}". Available fields: {2}.</source>
      <translation>La couche « {0} » n’a pas de champ « {1} ». Champs disponibles : {2}.</translation>
    </message>
    <message>
      <source>Layer "{0}" has nothing inside the frame.</source>
      <translation>La couche « {0} » n’a rien dans le cadre.</translation>
    </message>
    <message>
      <source>Layer "{0}" holds no polygons: grouping ignored.</source>
      <translation>La couche « {0} » ne contient pas de polygones : regroupement ignoré.</translation>
    </message>
    <message>
      <source>Layer "{0}" is drawn without symbols: its shapes are written unstyled, to carry their names.</source>
      <translation>La couche « {0} » est dessinée sans symbole : ses formes sont écrites sans style, pour porter leurs noms.</translation>
    </message>
    <message>
      <source>Layer "{0}" is drawn without symbols: only its labels are exported.</source>
      <translation>La couche « {0} » est dessinée sans symbole : seules ses étiquettes sont exportées.</translation>
    </message>
    <message>
      <source>Layer "{0}" is hidden at this scale.</source>
      <translation>La couche « {0} » est masquée à cette échelle.</translation>
    </message>
    <message>
      <source>Layer "{0}" is not a vector layer and was skipped.</source>
      <translation>La couche « {0} » n’est pas vectorielle : ignorée.</translation>
    </message>
    <message>
      <source>Layer "{0}" is not among the exported layers. Available: {1}.</source>
      <translation>La couche « {0} » ne fait pas partie des couches exportées. Disponibles : {1}.</translation>
    </message>
    <message>
      <source>Layer "{0}" produced no image.</source>
      <translation>La couche « {0} » n’a produit aucune image.</translation>
    </message>
    <message>
      <source>Layer "{0}" would render as {1} x {2} pixels: lower the image resolution.</source>
      <translation>La couche « {0} » ferait {1} x {2} pixels : baissez la résolution des images.</translation>
    </message>
    <message>
      <source>Layer "{0}": could not encode the image.</source>
      <translation>Couche « {0} » : encodage de l’image impossible.</translation>
    </message>
    <message>
      <source>Layer "{0}": dropped {1}.</source>
      <translation>Couche « {0} » : écartées, {1}.</translation>
    </message>
    <message>
      <source>Layer "{0}": no feature matched its symbology ({1} renderer). Check its rules or categories.</source>
      <translation>Couche « {0} » : aucune entité ne correspond à sa symbologie (rendu {1}). Vérifiez ses règles ou ses catégories.</translation>
    </message>
    <message>
      <source>Layer "{0}": value {1} covers several names ({2}); the first is used.</source>
      <translation>Couche « {0} » : la valeur {1} couvre plusieurs noms ({2}) ; le premier est retenu.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} classes, {2} named groups{3}.</source>
      <translation>Couche « {0} » : {1} classes, {2} groupes nommés{3}.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} shapes kept as separate paths so that merging them would not exceed the vertex limit.</source>
      <translation>Couche « {0} » : {1} formes gardées en tracés séparés pour que leur fusion ne dépasse pas la limite de sommets.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} shapes simplified, tolerance up to {2} mm.</source>
      <translation>Couche « {0} » : {1} formes simplifiées, tolérance jusqu’à {2} mm.</translation>
    </message>
    <message>
      <source>Layer "{0}": {1} shapes too dense for one path were cut into tiles that pave the same surface, with their outline drawn apart. No vertex was lost.</source>
      <translation>Couche « {0} » : {1} formes trop denses pour un seul tracé ont été découpées en dalles qui pavent la même surface, contour dessiné à part. Aucun sommet perdu.</translation>
    </message>
    <message>
      <source>Layer to split into named groups (e.g. countries)</source>
      <translation>Couche à découper en groupes nommés (ex. les pays)</translation>
    </message>
    <message>
      <source>Layers</source>
      <translation>Couches</translation>
    </message>
    <message>
      <source>Layers to export (empty = those shown in the frame)</source>
      <translation>Couches à exporter (vide = celles du cadre)</translation>
    </message>
    <message>
      <source>Layout "{0}": page {1} x {2} mm, frame {3} x {4} mm, placement {5}, map rotation {6}°, scale 1:{7}, CRS {8}.</source>
      <translation>Mise en page « {0} » : page {1} x {2} mm, cadre {3} x {4} mm, placement {5}, rotation de la carte {6}°, échelle 1:{7}, SCR {8}.</translation>
    </message>
    <message>
      <source>Legend</source>
      <translation>Légende</translation>
    </message>
    <message>
      <source>Legend "{0}" could not be rendered: {1}</source>
      <translation>La légende « {0} » n’a pas pu être rendue : {1}</translation>
    </message>
    <message>
      <source>Legend "{0}" embedded as vectors.</source>
      <translation>Légende « {0} » intégrée en vectoriel.</translation>
    </message>
    <message>
      <source>Map</source>
      <translation>Carte</translation>
    </message>
    <message>
      <source>Map frame</source>
      <translation>Cadre de carte</translation>
    </message>
    <message>
      <source>Map to grouped SVG</source>
      <translation>Carte vers SVG groupé</translation>
    </message>
    <message>
      <source>Maximum simplification allowed (mm on the page)</source>
      <translation>Simplification maximale autorisée (mm sur la page)</translation>
    </message>
    <message>
      <source>Maximum vertices per shape (0 = no limit)</source>
      <translation>Nombre maximal de sommets par forme (0 = sans limite)</translation>
    </message>
    <message>
      <source>Minimum polygon area (mm² on the page)</source>
      <translation>Surface minimale des polygones (mm² sur la page)</translation>
    </message>
    <message>
      <source>Name field</source>
      <translation>Champ nom</translation>
    </message>
    <message>
      <source>Naming</source>
      <translation>Nommage</translation>
    </message>
    <message>
      <source>No label is shown in the map frame.</source>
      <translation>Aucune étiquette n’est affichée dans le cadre de carte.</translation>
    </message>
    <message>
      <source>No layer to export.</source>
      <translation>Aucune couche à exporter.</translation>
    </message>
    <message>
      <source>No legend on the page of the map frame.</source>
      <translation>Aucune légende sur la page du cadre de carte.</translation>
    </message>
    <message>
      <source>No scale bar written: no latitude could be measured in this projection. First reason: {0}.</source>
      <translation>Aucune barre d’échelle écrite : aucune latitude n’a pu être mesurée dans cette projection. Première raison : {0}.</translation>
    </message>
    <message>
      <source>Note the projection under the bar</source>
      <translation>Noter la projection sous la barre</translation>
    </message>
    <message>
      <source>Nothing to export inside the map frame.</source>
      <translation>Rien à exporter à l’intérieur du cadre de carte.</translation>
    </message>
    <message>
      <source>Number of segments</source>
      <translation>Nombre de segments</translation>
    </message>
    <message>
      <source>Only latitudes shown on the map</source>
      <translation>Seulement les latitudes présentes sur la carte</translation>
    </message>
    <message>
      <source>Other layers to name (layer, name field, grouping field)</source>
      <translation>Autres couches à nommer (couche, champ nom, champ de regroupement)</translation>
    </message>
    <message>
      <source>Output</source>
      <translation>Sortie</translation>
    </message>
    <message>
      <source>Print layout</source>
      <translation>Mise en page</translation>
    </message>
    <message>
      <source>SVG file</source>
      <translation>Fichier SVG</translation>
    </message>
    <message>
      <source>Scale bar</source>
      <translation>Barre d’échelle</translation>
    </message>
    <message>
      <source>Scale bar caption</source>
      <translation>Légende de la barre d’échelle</translation>
    </message>
    <message>
      <source>Scale bar position from the left (mm, 0 = automatic)</source>
      <translation>Position de la barre depuis la gauche (mm, 0 = automatique)</translation>
    </message>
    <message>
      <source>Scale bar position from the top (mm, 0 = automatic)</source>
      <translation>Position de la barre depuis le haut (mm, 0 = automatique)</translation>
    </message>
    <message>
      <source>Scale bar text size (mm)</source>
      <translation>Taille du texte de la barre (mm)</translation>
    </message>
    <message>
      <source>Scale bar: centre longitude {0}°, measured on {1}.</source>
      <translation>Barre d’échelle : longitude du centre {0}°, mesures sur {1}.</translation>
    </message>
    <message>
      <source>Segment of {0} {1}: at {2}° it measures {3} mm on the page.</source>
      <translation>Segment de {0} {1} : à {2}°, il mesure {3} mm sur la page.</translation>
    </message>
    <message>
      <source>Select a map frame in that layout.</source>
      <translation>Choisissez un cadre de carte dans cette mise en page.</translation>
    </message>
    <message>
      <source>Select a print layout.</source>
      <translation>Choisissez une mise en page.</translation>
    </message>
    <message>
      <source>Separate islands into distinct paths</source>
      <translation>Séparer les îles en tracés distincts</translation>
    </message>
    <message>
      <source>The labels could not be rendered: {0}</source>
      <translation>Les étiquettes n’ont pas pu être rendues : {0}</translation>
    </message>
    <message>
      <source>The map frame has no coordinate reference system.</source>
      <translation>Le cadre de carte n’a pas de système de coordonnées.</translation>
    </message>
    <message>
      <source>The map frame has no size.</source>
      <translation>Le cadre de carte n’a pas de dimensions.</translation>
    </message>
    <message>
      <source>The map frame is degenerate.</source>
      <translation>Le cadre de carte est dégénéré.</translation>
    </message>
    <message>
      <source>The map frame is not on a page.</source>
      <translation>Le cadre de carte n’est sur aucune page.</translation>
    </message>
    <message>
      <source>The map frame outline is invalid.</source>
      <translation>Le contour du cadre de carte est invalide.</translation>
    </message>
    <message>
      <source>The symbology could not be released: {0}</source>
      <translation>La symbologie n’a pas pu être libérée : {0}</translation>
    </message>
    <message>
      <source>Unnamed</source>
      <translation>Sans nom</translation>
    </message>
    <message>
      <source>Written to {0}.</source>
      <translation>Écrit dans {0}.</translation>
    </message>
    <message>
      <source>below the minimum area</source>
      <translation>sous la surface minimale</translation>
    </message>
    <message>
      <source>class</source>
      <translation>classe</translation>
    </message>
    <message>
      <source>measurement refused ({0})</source>
      <translation>mesure refusée ({0})</translation>
    </message>
    <message>
      <source>none of the latitudes is on the map</source>
      <translation>aucune des latitudes n’est sur la carte</translation>
    </message>
    <message>
      <source>not drawn by the symbology</source>
      <translation>non dessinées par la symbologie</translation>
    </message>
    <message>
      <source>outside the frame</source>
      <translation>hors du cadre</translation>
    </message>
    <message>
      <source>reprojection failed</source>
      <translation>reprojection impossible</translation>
    </message>
    <message>
      <source>the result has no length</source>
      <translation>le résultat est de longueur nulle</translation>
    </message>
    <message>
      <source>the result, {0} mm, is far wider than the frame: the point falls outside what this projection can express</source>
      <translation>le résultat, {0} mm, dépasse de loin le cadre : le point tombe hors de ce que cette projection sait exprimer</translation>
    </message>
    <message>
      <source>the segment spans {0}° of longitude, more than the projection can show in one piece</source>
      <translation>le segment couvre {0}° de longitude, plus que ce que la projection peut montrer d’un seul tenant</translation>
    </message>
    <message>
      <source>unrepairable geometry</source>
      <translation>géométrie irréparable</translation>
    </message>
  </context>
</TS>
