# Eurekarto SVG Tools — 1.1.0

© 2026 Blanche Lambert / Eurêkarto  
Créé par Blanche Lambert pour Eurêkarto en 2026.  
Licence : GNU GPL v2 ou ultérieure (`GPL-2.0-or-later`).  
Contact : contact@eurekarto.com  
Code source et signalement de bugs : https://github.com/eurekarto/Eurekarto-SVG-Tools

## Installation

**Français** — Dans QGIS 3.40 LTR ou QGIS 4 : **Extensions → Installer/Gérer les extensions → Installer depuis un ZIP**. Sélectionnez `eurekarto_svg_tools-1_1_0.zip`, puis activez l'extension. L'outil apparaît dans le menu **Extensions → Eurekarto SVG Tools**, dans la barre d'outils des extensions, et dans la **boîte à outils de traitements**, fournisseur *Eurekarto SVG Tools*, groupe *Cartographie pour DAO*. Aucun paquet Python supplémentaire n'est nécessaire.

**English** — In QGIS 3.40 LTR or QGIS 4, use **Plugins → Manage and Install Plugins → Install from ZIP**, select `eurekarto_svg_tools-1_1_0.zip`, then enable the plugin. The tool appears under **Plugins → Eurekarto SVG Tools**, in the plugins toolbar, and in the **Processing toolbox**, provider *Eurekarto SVG Tools*, group *Cartography for CAD*. No additional Python packages are required.

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

L'outil n'exporte **ni étiquettes ni habillage** — le moteur d'étiquetage place le texte au rendu, cette information n'existe pas dans les données. Le mode de travail prévu est donc l'hybride : l'export SVG natif de la mise en page fournit étiquettes et habillage, cette extension fournit les couches vecteur structurées, et les deux fichiers se superposent au millimètre (*Coller sur place*).

## Paramètres

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

Les distances sont mesurées **le long des parallèles**, à la longitude du centre du cadre ; d'où la légende par défaut, à adapter si votre projection appelle une autre formulation. Le bloc est écrit sous un groupe `echelle`, hors du groupe `carte` : ses coordonnées sont des millimètres page, alors que le groupe carte porte le placement du cadre. Les réglages fins — nombre de segments, position, hauteur, taille du texte — sont dans les paramètres avancés.

## Tracés trop denses pour Illustrator

Illustrator n'ouvre pas un tracé de plus de 10 000 sommets environ : la forme disparaît silencieusement. Le paramètre **Nombre maximal de sommets par forme** (10 000 par défaut) détecte le cas après découpage et fusion, puis simplifie la géométrie par Douglas-Peucker avec une tolérance exprimée en millimètres sur la page, en partant de 0,01 mm et en doublant jusqu'à passer sous la limite. La tolérance retenue est indiquée dans le journal ; à 0,01 mm la perte est inférieure à la précision d'impression. Le comptage porte sur le tracé réellement écrit : total de l'entité en tracé composé, sommet le plus lourd de chaque partie si l'option de séparation des îles est active — activer cette option est d'ailleurs l'autre façon de passer sous la limite sans rien simplifier. Mettez 0 pour désactiver la réduction.

## Limites connues

- Seul le premier niveau de chaque symbole est lu : hachures, dégradés, contours multiples et formes de marqueurs ressortent en aplats et traits simples, avec la bonne couleur.
- Une entité qu'aucune classe ne couvre n'est pas exportée, comme sur la carte ; le journal la compte sous « non dessinées par la symbologie ».
- Un pays dont les entités relèvent de deux classes apparaît une fois dans chaque classe.
- Les identifiants XML sont repliés en ASCII et rendus uniques ; le nom d'origine reste dans `data-name` et dans `<title>`.
- Dans Illustrator, une image encodée en base64 peut apparaître liée : **Fenêtre → Liens → Incorporer** si nécessaire.

## Journal

Le journal d'exécution indique les valeurs de calage lues, le nombre de classes et de groupes écrits par couche, et chaque entité écartée avec sa raison : hors du cadre, reprojection impossible, géométrie irréparable, sous la surface minimale, non dessinée par la symbologie. En cas d'annulation, le SVG partiel est écrit et signalé comme incomplet.

## Mise à jour depuis une version installée

**Extensions → Installer/Gérer les extensions → Installer depuis un ZIP**, sélectionnez le nouveau ZIP et validez : QGIS remplace le dossier existant. Redémarrez ensuite QGIS — le code Python déjà chargé reste en mémoire, et le fournisseur de traitements n'est réenregistré proprement qu'au redémarrage. Si l'ancienne version persiste, vérifiez qu'il n'existe qu'un dossier `eurekarto_svg_tools` dans `python/plugins` du profil actif.

## Historique

- **1.1.0** — Barre d'échelle variable optionnelle, écrite dans le même SVG à côté du groupe `carte`.
- **1.0.3** — Dépôt, page d'accueil et suivi des bugs déclarés dans les métadonnées.
- **1.0.2** — Revue de code : placement du groupe carte par la transformation de scène du cadre (un cadre pivoté se plaçait au mauvais endroit), icône de barre d'outils de nouveau enregistrée, accès aux énumérations compatible Qt 5 et Qt 6, test du type de couche par classe plutôt que par une énumération obsolète, 33 tests unitaires.
- **1.0.1** — Réduction automatique des sommets au-delà d'un seuil (10 000 par défaut), pour les tracés qu'Illustrator refuse d'ouvrir. Tolérance en millimètres sur la page, indiquée dans le journal.
- **1.0.0** — Première version.

## Vérifications effectuées

- **Tests unitaires** : 40 tests couvrant le calage (y compris cadre pivoté), l'écriture des tracés, les identifiants XML, la réduction des sommets, la surface minimale, les clés de regroupement, la lecture des styles, la formule de la barre d'échelle contrôlée contre les longueurs géodésiques publiées, et la bonne formation du document SVG. Ils s'exécutent hors QGIS, sur des doublures minimales : `python3 test_svg_export.py`.
- **Analyse statique** : `pyflakes` et `flake8` (lignes ≤ 100 caractères, complexité ≤ 12) ne signalent rien.
- **Traductions** : 81 chaînes, générées depuis les appels `tr()` réellement présents dans le code, compilées avec `lrelease` et chargement vérifié ; aucune chaîne manquante ni orpheline, champs de substitution cohérents entre les deux langues.

## Publication sur plugins.qgis.org

Les champs exigés par le dépôt officiel sont renseignés : `name`, `qgisMinimumVersion`, `description`, `about`, `version`, `author`, `email`, `repository`, et le fichier `LICENSE` est présent. Le dépôt doit être public au moment de la validation. L'auteur déclaré est repris d'Eurekarto Projection Tools ; à corriger si l'attribution diffère.
