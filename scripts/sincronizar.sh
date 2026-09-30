#!/usr/bin/env bash
# Prepara el árbol de PROETI Asistencia para una versión de RustDesk y deja
# hecho el commit y la etiqueta `proeti-<versión>-r<revisión>`. NO sube nada:
# eso lo hace quien llama (el workflow sincronizar.yml, o a mano con git push).
#
# Uso:  scripts/sincronizar.sh [versión|latest] [carpeta]
#
# El commit es HUÉRFANO (sin la historia de RustDesk): el árbol completo de esa
# versión más nuestros cambios. Así el repo no arrastra cientos de MB de
# historia ajena, y cada etiqueta es exactamente el código que se compiló (que
# es lo que la AGPL pide poder entregar).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
VER="${1:-latest}"
ARBOL="${2:-$RAIZ/arbol}"

if [ "$VER" = latest ]; then
    VER=$(curl -fsSL https://api.github.com/repos/rustdesk/rustdesk/releases/latest \
          | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
fi
REV=$(tr -d '[:space:]' < "$RAIZ/REVISION")
TAG="proeti-$VER-r$REV"

rm -rf "$ARBOL"
git -c advice.detachedHead=false clone -q --depth 1 --branch "$VER" \
    https://github.com/rustdesk/rustdesk.git "$ARBOL"
python3 "$RAIZ/scripts/aplicar_branding.py" "$ARBOL" --version "$VER" --revision "$REV"

cd "$ARBOL"
# El submódulo libs/hbb_common se queda como enlace (gitlink) al commit que
# fija RustDesk; el checkout de la compilación lo trae de su repo.
git checkout -q --orphan proeti
git add -A
# El .gitignore de RustDesk ignora `*png`: los ficheros NUEVOS de branding/
# (logo_light.png, logo_dark.png, icon.png) no entrarían sin forzarlos, y el
# build saldría sin logo sin dar ningún error.
(cd "$RAIZ/branding" && find . -type f -print0) | xargs -0 git add -f --
git -c user.name="PROETI Asistencia" -c user.email="noreply@proetisa.com" \
    commit -q -m "PROETI Asistencia r$REV sobre RustDesk $VER"
git tag "$TAG"
echo "TAG=$TAG"
echo "VER=$VER"
