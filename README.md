# Eurekarto SVG Tools — 1.6.0

© 2026 Blanche Lambert / Eurêkarto  
Créé par Blanche Lambert pour Eurêkarto en 2026.  
Licence : GNU GPL v2 ou ultérieure (`GPL-2.0-or-later`).  
Contact : contact@eurekarto.com  
Code source et signalement de bugs : https://github.com/eurekarto/Eurekarto-SVG-Tools

## Installation

**Français** — Dans QGIS 3.40 LTR ou QGIS 4 : **Extensions → Installer/Gérer les extensions → Installer depuis un ZIP**. Sélectionnez `eurekarto_svg_tools-1_6_0.zip`, puis activez l'extension. L'outil apparaît dans le menu **Extensions → Eurekarto SVG Tools**, dans la barre d'outils des extensions, et dans la **boîte à outils de traitements**, fournisseur *Eurekarto SVG Tools*, groupe *Cartographie pour DAO*. Aucun paquet Python supplémentaire n'est nécessaire.

**English** — In QGIS 3.40 LTR or QGIS 4, use **Plugins → Manage and Install Plugins → Install from ZIP**, select `eurekarto_svg_tools-1_6_0.zip`, then enable the plugin. The tool appears under **Plugins → Eurekarto SVG Tools**, in the plugins toolbar, and in the **Processing toolbox**, provider *Eurekarto SVG Tools*, group *Cartography for CAD*. No additional Python packages are required.

Le ZIP contient exactement un dossier racine, `eurekarto_svg_tools`. Pour une installation manuelle, copiez ce dossier dans le répertoire `python/plugins` du profil QGIS actif et redémarrez QGIS. L'interface suit la langue de QGIS : française si QGIS est en français, anglaise sinon.

## Ce que fait l'outil

Écrit un cadre de carte de mise en page dans un seul fichier SVG structuré, destiné à être repris dans Illustrator ou Inkscape :

- **un groupe par couche**, dans l'ordre de la carte (couche du bas écrite en premier) ;
- **un groupe par classe** de symbologie catégorisée, graduée ou basée sur des règles, nommé d'après son libellé de légende, portant les couleurs et épaisseurs lues dans le symbole ;
- **un groupe nommé par entité** sur la couche de votre choix, d'après un champ — les pays arrivent en « France », « Espagne » ;
- **fusion facultative** des polygones partageant un code (ISO par exemple) : un pays et ses îles forment un seul objet.

Les rasters sont dessinés par QGIS et intégrés en images PNG transparentes. Les géométries sont réparées (`makeValid`) puis découpées géométriquement sur le cadre, donc le fichier ne contient **aucun masque d'écrêtage**.

## Calage sur la mise en page

Le fichier est écrit en millimètres à la taille de la page, la carte placée exactement là où se trouve le cadre. Taille de page, taille et position du cadre, emprise, rotation de la carte, rotation de l'objet et SCR sont lus dans la mise en page : rien à saisir, et il suffit de relancer après avoir déplacé le cadre ou changé l'échelle.

L'outil n'exporte pas l'habillage de la mise en page, hormis les étiquettes, les légendes et la barre d'échelle — le moteur d'étiquetage place le texte au rendu, cette information n'existe pas dans les données. Le mode de travail prévu est donc l'hybride : l'export SVG natif de la mise en page fournit étiquettes et habillage, cette extension fournit les couches vecteur structurées, et les deux fichiers se superposent au millimètre (*Coller sur place*).

## Paramètres

Les libellés portent leur section en préfixe — **Carte**, **Couches**, **Nommage**, **Apparence**, **Géométrie**, **Barre d'échelle**, **Sortie** — parce que la fenêtre de Processing ne sait pas afficher de titres de section. Les réglages fins sont dans le repli *Paramètres avancés*.

| Paramètre | Rôle |
|---|---|
| Mise en page / Cadre de carte | Source du calage et des couches à exporter |
| Couches à exporter | Vide = exactement ce que le cadre affiche |
| Couche à découper en groupes nommés | La couche des pays, en général |
| Champ qui porte les noms | Donne son nom à chaque groupe |
| Champ qui regroupe les polygones | Fusionne les polygones de même valeur (code ISO) |
| Autres couches à nommer | Table à trois colonnes pour les couches supplémentaires |
| Garder les couleurs et les classes de QGIS | Lit la symbologie ; décoché, aplats gris |
| Intégrer les images (rasters) | Rendu PNG embarqué, résolution réglable |
| Couper au bord du cadre | Intersection géométrique réelle |
| Surface minimale des polygones | Supprime la poussière d'îlots, en mm² sur la page |
| Précision des coordonnées | Décimales conservées dans les tracés |
| Taille des points par défaut | Rayon des cercles quand le symbole ne le donne pas |
| Séparer les îles en tracés distincts | Sinon un seul tracé composé par entité |
| Ajouter une barre d'échelle variable | Écrit un groupe `echelle` à côté du groupe `carte` |
| Latitudes à représenter | Une barre par latitude, séparées par des virgules |
| Distance par segment | En kilomètres ; 0 choisit une valeur ronde |
| Nombre maximal de sommets par forme | Simplifie automatiquement au-delà ; 0 désactive |

## Barre d'échelle variable

Sur une carte à petite échelle, le facteur d'échelle change d'un endroit à l'autre : une barre unique ne peut pas être juste partout. L'option trace une barre par latitude, chacune montrant la même distance réelle mesurée le long de son propre parallèle — leurs longueurs différentes sont le message.

Le calcul part du rayon de courbure en grande normale de l'ellipsoïde, et non de `QgsDistanceArea`, qui ne mesure rien du tout lorsqu'il ne parvient pas à résoudre un nom d'ellipsoïde : c'est exactement ce qui arrive avec une projection sur sphère comme les ESRI 53xxx. L'ellipsoïde retenu est celui du projet, sinon celui du SCR de la carte, sinon WGS84, et le journal indique lequel a servi. La formule a été contrôlée contre les longueurs géodésiques publiées du degré de longitude.

Les distances sont mesurées **le long des parallèles**, à la longitude du centre du cadre ; d'où la légende par défaut, à adapter si votre projection appelle une autre formulation. L'option *Seulement les latitudes présentes sur la carte*, active par défaut, teste si le parallèle traverse le cadre à la longitude de mesure et écarte les autres : une barre à 75° sur une carte qui s'arrête à 60° annoncerait une échelle invérifiable. Chaque latitude écartée est signalée dans le journal. Sous les barres viennent la légende puis, si l'option est cochée, le nom de la projection suivi de son code — « Sphere Equal Earth Greenwich (ESRI:53036) » — car une barre variable n'a de sens qu'avec la projection à laquelle elle se rapporte. Le bloc est écrit sous un groupe `echelle`, hors du groupe `carte` : ses coordonnées sont des millimètres page, alors que le groupe carte porte le placement du cadre. Les réglages fins — nombre de segments, position, hauteur, taille du texte — sont dans les paramètres avancés.

## Étiquettes

Les étiquettes du cadre de carte sont intégrées sous un groupe `etiquettes`, placé juste au-dessus du groupe `carte`, avec **un sous-groupe par couche** (`etiquettes_<couche>`). Ce découpage passe par le rendu par étapes, celui qu'utilise QGIS pour son propre export SVG en calques : le moteur d'étiquetage résout les collisions sur l'ensemble de la carte, comme il le ferait pour un rendu unique, mais rend les étiquettes couche par couche. Ce rendu n'est pas lié à Python dans toutes les versions : QGIS 3.40 sur macOS, par exemple, ne l'expose pas. Une seconde voie prend alors le relais. Un premier rendu complet demande au moteur où il place chaque étiquette, et de quelle couche elle vient. Chaque couche est ensuite rendue seule, les étiquettes des autres couches étant déclarées comme **zones interdites** : les siennes se replacent donc là où elles étaient quand toutes les couches étaient en jeu. Le coût est un rendu par couche étiquetée, et le placement peut varier très légèrement. Si cette voie n'est pas disponible non plus, les étiquettes sont écrites ensemble et le journal en donne la raison. Tous ces imports sont protégés : une classe manquante ne peut pas empêcher l'extension de se charger. Elles sont placées par le moteur d'étiquetage de QGIS, avec les réglages du cadre — couches, thème, rotation, paramètres d'étiquetage — et rendues sans les symboles, à la résolution d'impression. Le texte reste du texte lorsque l'étiquetage le permet ; les tampons et ombres sortent en tracés. Le fragment est nettoyé avant d'être greffé : le moteur de rendu pose sous chaque passe un fond de la taille du canevas, transparent pour lui mais écrit avec une opacité nulle qu'Illustrator ignore — il arriverait en feuille blanche —, et Qt ouvre un groupe à chaque changement d'état du peintre, même quand rien n'est dessiné. Ces fonds sont retirés au moment de la greffe, sur le seul groupe `etiquettes`, selon deux critères complémentaires : une forme sans remplissage ni contour visibles, et une forme — même opaque — qui couvre toute la page une fois appliquée la transformation de son groupe. Ce second calcul compte, car Qt écrit souvent ces fonds dans un groupe réduit ou agrandi, où leur taille apparente ne correspond plus à la page.

Une couche qui a une opacité, un mode de fusion ou des effets est par ailleurs dessinée d'abord dans une image intermédiaire de la taille du canevas ; symboles désactivés, cette image reste vide mais serait écrite, et Illustrator l'afficherait en feuille blanche. Le rendu des étiquettes force donc la sortie vectorielle, et toute image intégrée entièrement transparente est retirée par sécurité. Le contrôle porte sur chaque pixel, sans échantillonnage : une image est jugée vide lorsque aucun pixel n'atteint 5/255 d'opacité (environ 2 %), seuil sous lequel rien ne se voit à l'impression ; en ARGB prémultiplié, la couleur d'un pixel ne dépasse jamais son opacité. Une ombre ou une étiquette rastérisée, dont le cœur est bien plus dense, est toujours conservée.

Reste le cas d'une couche étiquetée qui utilise un mode de fusion : le générateur SVG ne sachant pas fusionner, QGIS aplatit cette couche en image, et symboles désactivés il n'en reste qu'un fond opaque, généralement blanc. Dans le groupe `etiquettes` — et là seulement, puisque les étiquettes y sont en texte — une image qui couvre toute la page d'une seule couleur est donc retirée : elle ne porte aucun dessin. Une image uniforme plus petite que la page, ou une image qui contient le moindre tracé, est conservée. Une forme visible est toujours conservée, et un groupe contenant du texte ou une image n'est jamais touché. Le placement suit le même moteur que la mise en page, mais les collisions sont recalculées : sur une carte très chargée, une étiquette peut céder sa place à une autre. Décochez *Inclure les étiquettes* pour les laisser à l'export natif.

## Légendes

Les légendes visibles sur la page du cadre de carte sont intégrées, chacune sous un groupe `legende` placé exactement où elle se trouve dans la mise en page. Elles ne sont pas redessinées : QGIS les peint lui-même dans un générateur SVG, comme pour l'export natif, puis le résultat est greffé dans le fichier. Symboles, polices, espacements et cadre sont donc ceux que vous voyez, et les textes restent des éléments `<text>` éditables — le format de texte de la mise en page est basculé en texte le temps du rendu, puis rétabli. Il faut que les polices soient installées sur le poste qui ouvre le fichier. Décochez *Inclure les légendes de la mise en page* pour les laisser à l'export natif.

## Symboles de points

Le marqueur de chaque classe est dessiné **une fois par QGIS**, dans un générateur SVG, puis copié à l'emplacement de chaque point. Toutes les formes de base (carré, triangle, étoile, croix…) sont donc restituées telles quelles, comme les marqueurs SVG et les marqueurs de police. Les valeurs pilotées par les données — une taille ou une rotation lue dans un champ — ne sont pas appliquées : chaque classe montre son symbole tel qu'il est défini.

Chaque figuré est écrit comme **un seul groupe**, portant sa position et son style. Qt ouvre un groupe pour ses valeurs par défaut et un autre pour l'état du peintre, et le placement en ajoutait un troisième : un groupe qui ne contient qu'un groupe est fusionné avec lui, attributs combinés et transformations enchaînées, l'intérieur l'emportant sur l'extérieur. Un groupe contenant plusieurs éléments n'est jamais touché, et un fragment mal formé est laissé tel quel.

Le **groupe nommé** d'une entité qui ne porte qu'un figuré le porte directement : son identifiant, son nom, sa position et son style tiennent sur un seul groupe, qui contient le tracé et le titre. Une entité comptant plusieurs figurés garde le sien pour chacun, et un polygone n'est pas concerné. Autour d'une forme, il ne reste donc que les niveaux qui ont un sens : la couche, la classe s'il y en a plusieurs, l'entité nommée.

Le rendu demande explicitement la **sortie vectorielle**, comme le fait l'export SVG natif de QGIS. Sans cela, tout symbole portant une opacité de niveau, un mode de fusion, une ombre ou un remplissage shapeburst est dessiné dans une image, et c'est cette image qui se retrouve dans le fichier. Si un effet ne peut vraiment pas être composé en vectoriel, le symbole reste une image, mais le journal nomme la classe concernée au lieu de l'intégrer en silence.

## Cartes de chaleur

Une couche en rendu *heatmap* ne dessine aucun symbole par entité : elle calcule une image de densité à partir des points. Il n'y a rien à regrouper ni à nommer ; elle est donc peinte par QGIS et intégrée en image, comme un raster, à la résolution choisie.

## Tracés trop denses pour Illustrator

Illustrator n'ouvre pas un tracé de plus de 10 000 sommets environ : la forme disparaît silencieusement. Le paramètre **Nombre maximal de sommets par forme** (10 000 par défaut) traite ce cas, mais jamais au prix de la forme.

Trois garde-fous. La simplification s'applique **partie par partie** : un continent dense ne coûte plus ses sommets à une petite île de la même entité. La tolérance Douglas-Peucker est **plafonnée** par *Simplification maximale autorisée*, 0,1 mm sur la page par défaut — en dessous de la précision d'impression. Et si aucune tolérance autorisée ne suffit, la forme est **découpée en dalles** qui pavent exactement la même surface : aucun sommet n'est perdu, et chaque tracé écrit reste sous la limite. Les dalles ne portent pas de contour, pour que leurs bords ne se voient jamais ; le contour d'origine est dessiné à part, en polylignes ouvertes qui se chevauchent d'un point pour rester continues.

Les parties ne sont fusionnées en un tracé composé que si le résultat tient sous la limite ; sinon elles restent des tracés distincts, ce qui préserve tous les sommets. Cocher *Séparer les îles en tracés distincts* force ce comportement. Mettez 0 pour désactiver entièrement la réduction.

## Limites connues

- Tous les niveaux d'un symbole sont lus, et leur type est distingué : un polygone dont le contour est un niveau de ligne garde ce contour au lieu d'être rempli de sa couleur, et une ligne conserve la sienne. En revanche le rendu reste un aplat et un trait : hachures, dégradés et formes de marqueurs ressortent simplifiés, avec la bonne couleur.
- Une entité qu'aucune classe ne couvre n'est pas exportée, comme sur la carte ; le journal la compte sous « non dessinées par la symbologie », et signale le type de rendu lorsqu'une couche entière ressort vide.
- Une couche réglée sur « Pas de symbole » ne donne que ses étiquettes ; si elle porte des groupes nommés, ses formes sont écrites sans remplissage ni contour, pour conserver les noms.
- Un pays dont les entités relèvent de deux classes apparaît une fois dans chaque classe.
- Les identifiants XML sont repliés en ASCII et rendus uniques ; le nom d'origine reste dans `data-name` et dans `<title>`.
- Dans Illustrator, une image encodée en base64 peut apparaître liée : **Fenêtre → Liens → Incorporer** si nécessaire.

## Journal

Le journal d'exécution indique les valeurs de calage lues, le nombre de classes et de groupes écrits par couche, et chaque entité écartée avec sa raison : hors du cadre, reprojection impossible, géométrie irréparable, sous la surface minimale, non dessinée par la symbologie. En cas d'annulation, le SVG partiel est écrit et signalé comme incomplet.

## Mise à jour depuis une version installée

**Extensions → Installer/Gérer les extensions → Installer depuis un ZIP**, sélectionnez le nouveau ZIP et validez : QGIS remplace le dossier existant. Redémarrez ensuite QGIS — le code Python déjà chargé reste en mémoire, et le fournisseur de traitements n'est réenregistré proprement qu'au redémarrage. Si l'ancienne version persiste, vérifiez qu'il n'existe qu'un dossier `eurekarto_svg_tools` dans `python/plugins` du profil actif.

## Historique

- **1.6.0** — Étiquettes groupées par couche, un seul groupe par figuré au lieu de trois ou quatre imbriqués. Sortie vectorielle forcée pour les symboles et les légendes : un marqueur portant une opacité ou un effet ressort en tracés au lieu d'une image intégrée.
- **1.5.0** — Légendes et étiquettes intégrées au SVG, rendues par QGIS lui-même. Les couches à rendu par ensemble de règles sont de nouveau exportées. Une couche « Pas de symbole » donne ses étiquettes, ou des formes sans style si elle porte des groupes nommés.
- **1.4.0** — La simplification ne déforme plus : elle travaille partie par partie et sa tolérance est plafonnée. Une forme qu'aucune tolérance autorisée ne peut alléger est écrite telle quelle et signalée. Illustrator tronque un tracé trop dense au lieu de le refuser, d'où ce découpage. Chaque polygone rendu par une réparation est écrit, y compris lorsque l'allègement d'un anneau l'a rendu auto-intersectant. Le remplissage suit la règle `nonzero` avec des anneaux orientés explicitement : les trous percent, et deux contours qui se recouvrent s'additionnent au lieu de s'annuler en un trou blanc.
- **1.3.1** — Plus aucune erreur avalée en silence : une emprise sans image dans le SCR de la couche retire le filtre spatial au lieu de ne rien lire, et un rendu qui refuse d'être libéré est signalé. Passe le contrôle de sécurité Bandit du dépôt QGIS.
- **1.3.0** — Les latitudes absentes de la carte ne reçoivent plus de barre.
- **1.2.0** — Paramètres regroupés par section dans la fenêtre, réglages fins basculés en avancés, nom de la projection écrit sous la barre d'échelle.
- **1.1.0** — Barre d'échelle variable optionnelle, écrite dans le même SVG à côté du groupe `carte`.
- **1.0.3** — Dépôt, page d'accueil et suivi des bugs déclarés dans les métadonnées.
- **1.0.2** — Revue de code : placement du groupe carte par la transformation de scène du cadre (un cadre pivoté se plaçait au mauvais endroit), icône de barre d'outils de nouveau enregistrée, accès aux énumérations compatible Qt 5 et Qt 6, test du type de couche par classe plutôt que par une énumération obsolète, 33 tests unitaires.
- **1.0.1** — Réduction automatique des sommets au-delà d'un seuil (10 000 par défaut), pour les tracés qu'Illustrator refuse d'ouvrir. Tolérance en millimètres sur la page, indiquée dans le journal.
- **1.0.0** — Première version.

## Vérifications effectuées

- **Tests unitaires** : 130 tests, dont onze sur la lecture des symboles couvrant le calage (y compris cadre pivoté), l'écriture des tracés, les identifiants XML, la réduction des sommets, la surface minimale, les clés de regroupement, la lecture des styles, la formule de la barre d'échelle contrôlée contre les longueurs géodésiques publiées, et la bonne formation du document SVG. Ils s'exécutent hors QGIS, sur des doublures minimales : `python3 test_svg_export.py`.
- **Analyse statique** : `pyflakes`, `flake8` (lignes ≤ 100 caractères, complexité ≤ 12) et `bandit` — l'analyseur de sécurité utilisé par le dépôt QGIS — ne signalent rien.
- **Traductions** : 95 chaînes, générées depuis les appels `tr()` réellement présents dans le code, compilées avec `lrelease` et chargement vérifié ; aucune chaîne manquante ni orpheline, champs de substitution cohérents entre les deux langues.
- **Non vérifié** : l'exécution réelle dans QGIS — renderers, itération sur les entités, rendu raster, compatibilité QGIS 4. À valider sur un projet réel avant diffusion.

## Publication sur plugins.qgis.org

Les champs exigés par le dépôt officiel sont renseignés : `name`, `qgisMinimumVersion`, `description`, `about`, `version`, `author`, `email`, `repository`, et le fichier `LICENSE` est présent. Le dépôt doit être public au moment de la validation. L'auteur déclaré est repris d'Eurekarto Projection Tools ; à corriger si l'attribution diffère.
