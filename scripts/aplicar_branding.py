#!/usr/bin/env python3
"""Aplica la imagen de PROETI Asistencia sobre un árbol limpio de RustDesk.

Uso:  python3 scripts/aplicar_branding.py <arbol> --version 1.4.9 --revision 1

Todo lo que toca está aquí, en un solo sitio, y cada cambio COMPRUEBA que el
texto original sigue existiendo exactamente como se esperaba. Si RustDesk
reorganiza su código en una versión nueva, el script se para con un mensaje
que dice qué fichero y qué cambio ya no encaja: nunca se publica un build
con el branding aplicado a medias.

Lo que NO se cambia, a propósito:
  - El nombre INTERNO (`APP_NAME` = "RustDesk"): decide las rutas de
    configuración (~/.config/rustdesk, /root/.config/rustdesk), el nombre del
    servicio y del paquete. En el equipo lo usan provision/40_services.sh,
    62_rustdesk_cm.sh, 80_cursor.sh, core/deviceid.php y el registro de
    seguridad. Solo cambia el nombre que se VE.
  - El servidor y su clave: no van en el repo (es público). Los pone
    `proeti/servidor.py` al compilar, a partir de los secrets de Actions.
"""
import argparse
import base64
import pathlib
import re
import shutil
import sys

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent

NOMBRE = "PROETI Asistencia"
NARANJA = "D05D27"   # botones (colores corporativos, CLAUDE.md §11)
NEGRO = "191718"     # cabeceras
NEGRO_2 = "3A3536"   # segundo tono del degradado de la tarjeta de conexión


class NoEncaja(Exception):
    pass


def sustituir(arbol, ruta, patron, nuevo, veces=1, que=""):
    """Sustituye `patron` (regex) por `nuevo` en `ruta`. Debe casar `veces` veces."""
    f = arbol / ruta
    texto = f.read_text(encoding="utf-8")
    encontrados = len(re.findall(patron, texto, flags=re.M))
    if encontrados != veces:
        raise NoEncaja(f"{ruta}: '{que}' casa {encontrados} veces (se esperaban {veces})")
    texto = re.sub(patron, nuevo, texto, flags=re.M)
    f.write_text(texto, encoding="utf-8", newline="\n")
    print(f"  ok  {ruta}: {que}")


def cambios_de_codigo(arbol):
    # 1. La tarjeta de la ventana de conexión (el recuadro que sale en la
    #    Odroid): degradado azul -> negro corporativo.
    sustituir(
        arbol, "flutter/lib/desktop/pages/server_page.dart",
        r"Color\(0xff00bfe1\),(\s*)Color\(0xff0071ff\),",
        rf"Color(0xff{NEGRO_2.lower()}),\1Color(0xff{NEGRO.lower()}),",
        que="degradado de la tarjeta de conexión",
    )
    # 2. Color de acento de toda la aplicación: azul -> naranja.
    common = "flutter/lib/common.dart"
    for nombre, alfa, original in [
        ("accent", "FF", "0071FF"),
        ("accent50", "77", "0071FF"),
        ("accent80", "AA", "0071FF"),
        ("button", "FF", "2C8CFF"),
        ("idColor", "FF", "00B6F0"),
    ]:
        sustituir(
            arbol, common,
            rf"(static const Color {nombre} = Color\(0x){alfa}{original}\);",
            rf"\g<1>{alfa}{NARANJA});",
            que=f"MyTheme.{nombre}",
        )
    # 3. Nombre visible (títulos de ventana, textos). NO toca APP_NAME.
    for fn, envoltura in [
        ("main_get_app_name() -> String", "{}"),
        ("main_get_app_name_sync() -> SyncReturn<String>", "SyncReturn({})"),
    ]:
        cuerpo = envoltura.format("get_app_name()")
        nuevo = envoltura.format(f'"{NOMBRE}".to_owned()')
        sustituir(
            arbol, "src/flutter_ffi.rs",
            rf"(pub fn {re.escape(fn)} \{{\s*){re.escape(cuerpo)}",
            rf"\g<1>{nuevo}",
            que=f"nombre visible en {fn.split('(')[0]}",
        )
    # 4. Sin aviso de "nueva versión de RustDesk": ofrecería instalar el
    #    paquete OFICIAL encima del nuestro. Las versiones las publicamos
    #    nosotros.
    sustituir(
        arbol, "src/common.rs",
        r"(pub fn check_software_update\(\) \{\s*)if is_custom_client\(\) \{",
        r"\g<1>// PROETI Asistencia: las actualizaciones las publica PROETI.\n    if true {",
        que="aviso de actualización desactivado",
    )
    # 5. Entrada de escritorio.
    sustituir(arbol, "res/rustdesk.desktop", r"^Name=RustDesk$", f"Name={NOMBRE}",
              que="Name del .desktop")
    sustituir(arbol, "res/rustdesk.desktop", r"^GenericName=Remote Desktop$",
              "GenericName=Asistencia remota", que="GenericName del .desktop")
    sustituir(arbol, "res/rustdesk.desktop", r"^Comment=Remote Desktop$",
              "Comment=Asistencia remota de PROETI", que="Comment del .desktop")


def svg_con_png(png):
    datos = base64.b64encode(png.read_bytes()).decode()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" width="512" height="512" '
        'viewBox="0 0 512 512">'
        f'<image width="512" height="512" xlink:href="data:image/png;base64,{datos}"/>'
        "</svg>\n"
    )


def imagenes(arbol):
    origen = RAIZ / "branding"
    for f in sorted(origen.rglob("*")):
        if f.is_file():
            destino = arbol / f.relative_to(origen)
            if not destino.parent.is_dir():
                raise NoEncaja(f"no existe la carpeta de destino {destino.parent.relative_to(arbol)}")
            shutil.copyfile(f, destino)
            print(f"  ok  {destino.relative_to(arbol)}")
    # Los SVG (icono del escritorio y reserva del icono de la app) llevan el
    # mismo PNG dentro: así no hay que mantener dos dibujos.
    svg = svg_con_png(origen / "res" / "icon.png")
    for ruta in ["res/scalable.svg", "flutter/assets/icon.svg"]:
        if not (arbol / ruta).is_file():
            raise NoEncaja(f"{ruta} ya no existe")
        (arbol / ruta).write_text(svg, encoding="utf-8", newline="\n")
        print(f"  ok  {ruta}")


# ── Workflow de compilación ─────────────────────────────────────────────────
# Se GENERA a partir del flutter-build.yml de la propia versión de RustDesk:
# así, cuando ellos cambian la receta (Flutter, vcpkg, dependencias), la
# nuestra cambia sola. Solo se queda con el job de Linux arm64.

def _repr_str(dumper, s):
    if "\n" in s:
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", s)


yaml.SafeDumper.add_representer(str, _repr_str)


def _cargar(f):
    wf = yaml.safe_load(f.read_text(encoding="utf-8"))
    if True in wf:  # YAML 1.1 lee la clave `on:` como booleano
        wf["on"] = wf.pop(True)
    return wf


def _volcar(wf, f, cabecera):
    texto = yaml.safe_dump(wf, sort_keys=False, width=10000, allow_unicode=True)
    f.write_text(cabecera + texto, encoding="utf-8", newline="\n")


def workflows(arbol, version, revision):
    wfdir = arbol / ".github" / "workflows"
    fb = _cargar(wfdir / "flutter-build.yml")

    job = fb["jobs"].get("build-rustdesk-linux")
    if not job:
        raise NoEncaja("flutter-build.yml ya no tiene el job build-rustdesk-linux")
    matriz = [j for j in job["strategy"]["matrix"]["job"] if j.get("arch") == "aarch64"]
    if len(matriz) != 1:
        raise NoEncaja(f"build-rustdesk-linux: {len(matriz)} entradas aarch64 en la matriz (se esperaba 1)")
    job["strategy"]["matrix"]["job"] = matriz

    pasos = job["steps"]
    i = next((n for n, p in enumerate(pasos) if p.get("name") == "Checkout source code"), None)
    if i is None:
        raise NoEncaja("build-rustdesk-linux: no está el paso 'Checkout source code'")
    pasos.insert(i + 1, {
        "name": "Servidor de asistencia de PROETI",
        "env": {
            "PROETI_RENDEZVOUS_SERVER": "${{ secrets.PROETI_RENDEZVOUS_SERVER }}",
            "PROETI_RS_PUB_KEY": "${{ secrets.PROETI_RS_PUB_KEY }}",
        },
        "run": "python3 proeti/servidor.py libs/hbb_common/src/config.rs\n",
    })
    # Arch Linux es solo x86_64: fuera.
    job["steps"] = [p for p in pasos if "archlinux" not in p.get("name", "").lower()]

    env = fb["env"]
    env["TAG_NAME"] = "${{ github.ref_name }}"
    env["UPLOAD_ARTIFACT"] = "true"

    compilar = {
        "name": f"{NOMBRE} — compilar (arm64)",
        "on": {"push": {"tags": ["proeti-*"]}, "workflow_dispatch": {}},
        "permissions": {"contents": "write"},
        "env": env,
        "jobs": {
            "generate-bridge": fb["jobs"]["generate-bridge"],
            "build-rustdesk-linux": job,
        },
    }

    # El bridge: solo el de Flutter 3.24 (el de 3.44 es para Windows arm64).
    bridge = _cargar(wfdir / "bridge.yml")
    bm = bridge["jobs"]["generate_bridge"]["strategy"]["matrix"]["job"]
    bm = [j for j in bm if j.get("artifact-name") == "bridge-artifact"]
    if len(bm) != 1:
        raise NoEncaja("bridge.yml: no se encuentra la entrada 'bridge-artifact'")
    bridge["jobs"]["generate_bridge"]["strategy"]["matrix"]["job"] = bm

    # Fuera todos los demás workflows de RustDesk: en este repo no deben
    # dispararse (ni compilar Windows/Android/iOS, ni pedir sus secrets).
    for f in wfdir.iterdir():
        f.unlink()
    aviso = (f"# GENERADO por scripts/aplicar_branding.py a partir de RustDesk {version}\n"
             f"# (PROETI Asistencia r{revision}). No editar aquí: se rehace en cada versión.\n")
    _volcar(compilar, wfdir / "compilar.yml", aviso)
    _volcar(bridge, wfdir / "bridge.yml", aviso)
    print("  ok  .github/workflows/compilar.yml (+ bridge.yml; el resto, fuera)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arbol")
    ap.add_argument("--version", required=True)
    ap.add_argument("--revision", required=True)
    a = ap.parse_args()
    arbol = pathlib.Path(a.arbol).resolve()

    print(f"PROETI Asistencia r{a.revision} sobre RustDesk {a.version}")
    try:
        cambios_de_codigo(arbol)
        imagenes(arbol)
        workflows(arbol, a.version, a.revision)
    except NoEncaja as e:
        print(f"\nERROR: el branding ya no encaja en RustDesk {a.version}: {e}", file=sys.stderr)
        print("Hay que adaptar scripts/aplicar_branding.py a esta versión.", file=sys.stderr)
        sys.exit(1)

    (arbol / "proeti").mkdir(exist_ok=True)
    shutil.copyfile(RAIZ / "scripts" / "servidor.py", arbol / "proeti" / "servidor.py")
    (arbol / "proeti" / "LEEME.md").write_text(
        f"# PROETI Asistencia r{a.revision}\n\n"
        f"Código de RustDesk {a.version} (https://github.com/rustdesk/rustdesk, AGPL-3.0)\n"
        "con la imagen de PROETI aplicada por `scripts/aplicar_branding.py`\n"
        "(rama `main` de este mismo repositorio).\n",
        encoding="utf-8", newline="\n")
    print("Hecho.")


if __name__ == "__main__":
    main()
