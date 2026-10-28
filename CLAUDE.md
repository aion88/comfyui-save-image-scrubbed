# comfyui-save-image-scrubbed

Nœud ComfyUI « Save Image (scrubbed) » : enregistre les PNG comme le Save Image natif, mais retire les clés API et autres identifiants des métadonnées embarquées. Publié en open source (MIT).

## Statut

- Actif, version initiale. Dernier commit de fond : 2026-10-27 (`Initial release: Save Image (scrubbed) ComfyUI node`).

## Stack

- Python `>=3.10`, sans dépendance d'exécution (utilise Pillow et numpy de ComfyUI). Dev : `pytest>=8`, `pillow>=10` (`pyproject.toml`, `uv.lock`).

## Commandes

- Tests : `uv run pytest` (17 tests d'après le README).
- Installation dans ComfyUI : `cd ComfyUI/custom_nodes && git clone https://github.com/aion88/comfyui-save-image-scrubbed`, puis redémarrer ComfyUI.

## Structure

- `nodes.py` : le nœud ComfyUI. `__init__.py` : enregistrement.
- `png_scrub.py` : logique de purge (liste des noms de champs, formes de valeurs).
- `tests/test_png_scrub.py` : tests unitaires sans ComfyUI.
- `.gitleaks.toml` : autorise les regex de détection du scrubber, qui ne sont pas des identifiants.

## Règles du projet

- `metadata=scrub` (défaut) garde le graphe rechargeable et masque par nom de champ (valeurs chaînes seulement) et par forme de valeur. `metadata=drop` n'écrit aucune métadonnée.
- Avant écriture, les octets finaux sont rescannés ; si une forme d'identifiant subsiste, le nœud lève `ScrubFailed` et n'écrit rien.
- Limites connues : un champ hors liste avec un jeton de forme inconnue passe ; le `workflow` stocke les widgets par position, donc seule la forme de la valeur l'attrape ; seuls les PNG de ce nœud sont purgés.
- Étendre la liste de champs dans `png_scrub.py` pour de nouveaux fournisseurs.

## Liens

- Dépôt distant : https://github.com/aion88/comfyui-save-image-scrubbed
