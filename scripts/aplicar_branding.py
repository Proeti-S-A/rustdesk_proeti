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


def sesion_en_la_cabecera(arbol):
    """La ventana de conexión no se enseña: la sesión la enseña la cabecera de la
    interfaz del equipo, y el chat un panel a la derecha (proeti_interfaz,
    core/asistencia.php).

    Son piezas que van juntas. Ocultar la ventana sin publicar quién está dentro
    dejaría al cliente sin saber que hay alguien en su máquina.
    """
    # 6. Ocultar la ventana. RustDesk ya sabe hacerlo (`hide_cm`, la parte de
    #    Flutter la respeta entera: main.dart y server_model.dart), pero solo lo
    #    permite a clientes de pago o con otro nombre interno, y el nuestro sigue
    #    siendo «RustDesk» a propósito. Además exige aceptar solo por contraseña
    #    permanente; aquí no hace falta: en el kiosko no hay nadie que pulse
    #    «Aceptar», así que una conexión sin contraseña se queda sin atender.
    #    `proeti-ver-recuadro = 'Y'` en [options] de RustDesk2.toml la vuelve a
    #    enseñar, por si algún día hiciera falta.
    sustituir(
        arbol, "src/ipc.rs",
        r'(\} else if name == "hide_cm" \{\n(\s*))'
        r"value = if crate::hbbs_http::sync::is_pro\(\) \|\| crate::common::is_custom_client\(\)\s*"
        r"\{\s*Some\(hbb_common::password_security::hide_cm\(\)\.to_string\(\)\)\s*"
        r"\} else \{\s*None\s*\};",
        r"\g<1>// PROETI Asistencia: la sesión se ve en la cabecera del equipo.\n"
        r'\g<2>value = Some((Config::get_option("proeti-ver-recuadro") != "Y").to_string());',
        que="ventana de conexión oculta (hide_cm)",
    )
    # 7. Publicar quién está dentro. El módulo es nuestro (codigo/src/); aquí solo
    #    se declara y se llama cuando entra o sale una conexión.
    destino = arbol / "src" / "proeti_asistencia.rs"
    if destino.exists():
        raise NoEncaja("src/proeti_asistencia.rs ya existe en RustDesk")
    shutil.copyfile(RAIZ / "codigo" / "src" / "proeti_asistencia.rs", destino)
    print("  ok  src/proeti_asistencia.rs")
    sustituir(
        arbol, "src/lib.rs", r"^mod ui_cm_interface;$",
        "mod ui_cm_interface;\n// PROETI Asistencia: quién está conectado, para la cabecera del equipo.\n"
        "mod proeti_asistencia;",
        que="declarar el módulo proeti_asistencia",
    )
    for funcion, llamada in [("add_connection", "add_connection(&client)"),
                             ("remove_connection", "remove_connection(id, close)")]:
        sustituir(
            arbol, "src/ui_cm_interface.rs",
            rf"^([ \t]*)self\.ui_handler\.{re.escape(llamada)};$",
            r"\g<0>\n\1crate::proeti_asistencia::publicar(&CLIENTS.read().unwrap());",
            que=f"publicar las sesiones en {funcion}",
        )
    # 8. El chat también va a la interfaz: lo que escribe el técnico se apunta
    #    para el panel del equipo (lo que escribe el equipo lo manda el propio
    #    módulo, con send_chat).
    sustituir(
        arbol, "src/ui_cm_interface.rs",
        r"^([ \t]*)self\.cm\.new_message\(self\.conn_id, text\);$",
        r"\1crate::proeti_asistencia::chat_entrante(self.conn_id, &text);\n\g<0>",
        que="apuntar el chat que llega del técnico",
    )
    # 9. Con la ventana oculta, RustDesk la volvería a sacar al llegar un mensaje
    #    de chat (showCmWindow sin mirar hideCm) o una llamada de voz
    #    (windowOnTop). El chat lo lleva la interfaz; la llamada de voz se queda
    #    sin contestar, como una conexión sin contraseña.
    sustituir(
        arbol, "flutter/lib/models/chat_model.dart",
        r"(if \(text\.isEmpty\) return;\n)([ \t]*)(if \(desktopType == DesktopType\.cm\) \{\n\s*await showCmWindow\(\);)",
        r"\1\2// PROETI Asistencia: con la ventana oculta, el chat lo lleva la interfaz del equipo.\n"
        r"\2if (desktopType == DesktopType.cm && session.serverModel.hideCm) return;\n\2\3",
        que="el chat no vuelve a sacar la ventana oculta",
    )
    sustituir(
        arbol, "flutter/lib/models/server_model.dart",
        r"(// Has incoming phone call, let's set the window on top\.\n\s*Future\.delayed\(Duration\.zero, \(\) \{\n\s*)"
        r"windowOnTop\(null\);",
        r"\1if (!hideCm) windowOnTop(null);",
        que="la llamada de voz no vuelve a sacar la ventana oculta",
    )
    # 10. (r4) Tampoco al ARRANCAR: el gestor de conexión arranca SIN interfaz.
    #     Con la ventana oculta (6), el gestor con Flutter (`--cm`) la enseñaba
    #     igual durante su arranque, unos 5 s en el Odroid: el lanzador de Linux
    #     la saca con opacidad 0 y sin compositor (el openbox del kiosko no tiene)
    #     eso no esconde nada. La r3 probó a no enseñarla (gtk_widget_realize) y
    #     el gestor ni siquiera llegaba a arrancar: cada conexión dejaba otro
    #     `--cm` colgado y nadie publicaba la sesión. Ahora el servicio lanza
    #     `--cm-no-ui`, el modo que RustDesk ya tiene para equipos sin
    #     escritorio: la misma lógica de conexiones (ConnectionManager, donde
    #     publica proeti_asistencia), solo Rust, sin Flutter ni ventana, y
    #     bastante menos memoria. Con `proeti-ver-recuadro = 'Y'`, el de siempre.
    sustituir(
        arbol, "src/server/connection.rs",
        r'^([ \t]*)let mut args = vec!\["--cm"\];$',
        r"\1// PROETI Asistencia: el gestor de conexión sin interfaz (la sesión y el chat\n"
        r"\1// los enseña la cabecera del equipo). Con proeti-ver-recuadro = 'Y', el de siempre.\n"
        r'\1let mut args = if Config::get_option("proeti-ver-recuadro") == "Y" {' "\n"
        r'\1    vec!["--cm"]' "\n"
        r"\1} else {" "\n"
        r'\1    vec!["--cm-no-ui"]' "\n"
        r"\1};",
        que="el gestor de conexión arranca sin interfaz",
    )


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


def _claves_on(x):
    """YAML 1.1 lee la clave `on:` como el booleano True. Pasa en la raíz del
    workflow y también DENTRO de la matriz de RustDesk (`on: ubuntu-22.04-arm`,
    que usa `runs-on: ${{ matrix.job.on }}`): si no se corrige en todas partes,
    el job se queda sin máquina y GitHub ni lo crea."""
    if isinstance(x, dict):
        return {("on" if k is True else k): _claves_on(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_claves_on(v) for v in x]
    return x


def _cargar(f):
    return _claves_on(yaml.safe_load(f.read_text(encoding="utf-8")))


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
        sesion_en_la_cabecera(arbol)
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
