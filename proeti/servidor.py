#!/usr/bin/env python3
"""Graba en el binario el servidor de asistencia de PROETI y su clave pública.

Lo ejecuta el workflow de compilación (viaja al árbol como proeti/servidor.py)
justo después del checkout, con los valores en variables de entorno que salen
de los secrets del repositorio:

  PROETI_RENDEZVOUS_SERVER   p. ej. support.proetisa.com
  PROETI_RS_PUB_KEY          clave PÚBLICA del hbbs (id_ed25519.pub)

La clave es pública por diseño (la lleva cada cliente); va en secrets solo
para que el repositorio no apunte a nuestro servidor. La PRIVADA no hace falta
aquí y no debe estar nunca en este repositorio ni en sus secrets.

Con esto el equipo usa nuestro servidor aunque se pierda RustDesk2.toml (pasaba
al sellar la imagen: los clones acababan en el servidor público de RustDesk).
"""
import os
import re
import sys


def main():
    config = sys.argv[1]
    host = os.environ.get("PROETI_RENDEZVOUS_SERVER", "").strip()
    key = os.environ.get("PROETI_RS_PUB_KEY", "").strip()
    if not host or not key:
        print("::error::Faltan los secrets PROETI_RENDEZVOUS_SERVER y/o PROETI_RS_PUB_KEY")
        sys.exit(1)
    if not re.fullmatch(r"[A-Za-z0-9.-]+(:\d+)?", host):
        print("::error::PROETI_RENDEZVOUS_SERVER no parece un nombre de servidor")
        sys.exit(1)
    if not re.fullmatch(r"[A-Za-z0-9+/]{43}=", key):
        print("::error::PROETI_RS_PUB_KEY no parece una clave Ed25519 en base64")
        sys.exit(1)

    with open(config, encoding="utf-8") as f:
        texto = f.read()
    for patron, nuevo, que in [
        (r'pub const RENDEZVOUS_SERVERS: &\[&str\] = &\[[^\]]*\];',
         f'pub const RENDEZVOUS_SERVERS: &[&str] = &["{host}"];', "RENDEZVOUS_SERVERS"),
        (r'pub const RS_PUB_KEY: &str = "[^"]*";',
         f'pub const RS_PUB_KEY: &str = "{key}";', "RS_PUB_KEY"),
    ]:
        texto, n = re.subn(patron, lambda _m: nuevo, texto)
        if n != 1:
            print(f"::error::{config}: {que} casa {n} veces (se esperaba 1); RustDesk ha cambiado de sitio la configuración")
            sys.exit(1)
        print(f"ok  {que}")
    with open(config, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    print(f"Servidor por defecto: {host}")


if __name__ == "__main__":
    main()
