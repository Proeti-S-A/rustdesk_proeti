# PROETI Asistencia

El programa de asistencia remota de las máquinas de PROETI. Es
[RustDesk](https://github.com/rustdesk/rustdesk) con la imagen de PROETI:
nombre, colores corporativos, logo e iconos. Además lleva nuestro servidor
grabado de fábrica.

Se mantiene al día solo: cada lunes se comprueba si RustDesk ha sacado versión
y, si la hay, se le aplica la imagen y se compila el `.deb` para las Odroid
(arm64).

## Qué cambia respecto a RustDesk

Todo está en [`scripts/aplicar_branding.py`](scripts/aplicar_branding.py):

| Qué | Dónde |
|---|---|
| La **tarjeta de conexión** que sale en la Odroid cuando alguien entra (usuario, ID, tiempo): de azul a negro corporativo | `server_page.dart` |
| El color de acento de toda la aplicación: de azul a naranja `#d05d27` | `MyTheme` en `common.dart` |
| El nombre que se ve: **PROETI Asistencia** | `main_get_app_name` |
| Logo (claro y oscuro), icono de la app, de la bandeja y del escritorio | [`branding/`](branding/) |
| Sin aviso de «hay una versión nueva de RustDesk» (instalaría el paquete oficial encima) | `check_software_update` |
| Servidor `support.proetisa.com` y su clave pública por defecto | [`scripts/servidor.py`](scripts/servidor.py), al compilar |

Hay cosas que **no cambian, a propósito**. El nombre interno sigue siendo
`rustdesk`, y con él el binario, el servicio, el paquete y la carpeta
`~/.config/rustdesk`. Las usa la provisión de las máquinas (`proeti_interfaz`:
`provision/40_services.sh`, `62_rustdesk_cm.sh`, `80_cursor.sh`,
`core/deviceid.php`). Gracias a eso, el paquete se instala encima del oficial
sin tocar nada más.

Cada cambio comprueba que el código original sigue como se esperaba. Si
RustDesk reorganiza algo, la sincronización **falla y abre un issue** diciendo
qué fichero ya no encaja. Nunca se publica un build con la imagen aplicada a
medias.

## Cómo funciona

```
main (este repo)                         etiqueta proeti-1.4.9-r1
├─ scripts/aplicar_branding.py   ──►     árbol COMPLETO de RustDesk 1.4.9
├─ scripts/servidor.py                   + nuestros cambios
├─ branding/                             + .github/workflows/compilar.yml
├─ REVISION                                (generado de SU flutter-build.yml,
└─ .github/workflows/sincronizar.yml        solo Linux arm64)
```

1. **`sincronizar.yml`** (lunes 05:00 UTC, o a mano desde Actions) mira la
   última versión de RustDesk. Si la etiqueta `proeti-<versión>-r<REVISION>` no
   existe, ejecuta `scripts/sincronizar.sh` y la sube.
2. La etiqueta es un **commit huérfano**: el código de esa versión con nuestros
   cambios, sin arrastrar la historia de RustDesk. Así, la etiqueta es
   exactamente el código que se compiló.
3. Subir la etiqueta dispara **`compilar.yml`**, que viaja dentro del árbol.
   Se genera a partir de la receta de compilación de la **propia versión** de
   RustDesk, así que cuando ellos cambian Flutter, vcpkg o las dependencias,
   la nuestra cambia sola. Compila en un runner arm64 nativo, dentro de un
   Ubuntu 18.04, igual que el paquete oficial. Por eso vale en toda la flota
   (focal, jammy y noble).
4. El `.deb` (`rustdesk-<versión>-aarch64.deb`) queda en una **pre-release**
   con el nombre de la etiqueta.

Para **cambiar la imagen** (otro color, otro logo), edita
`aplicar_branding.py` o `branding/` y sube `REVISION` en uno. La siguiente
sincronización lo recompila con la misma versión de RustDesk
(`proeti-1.4.9-r2`).

## Llevarlo a las máquinas: nunca automático

Compilar es automático; **instalar, no**. Un paquete roto instalado en toda la
flota dejaría todas las máquinas sin asistencia remota, que es justo la
herramienta con la que se arreglaría. El orden es:

1. Instalar la pre-release en **una** máquina y comprobar tres cosas: que
   entra una conexión, que la tarjeta se ve bien y que el equipo sigue en
   `support.proetisa.com` con su mismo ID.
2. Si todo va bien, marcar la versión como release (quitarle «pre-release»).
3. Después, el resto de la flota.

Instalar el paquete **reinicia RustDesk**: si estás dentro por RustDesk, la
sesión se corta. Hay que hacerlo en diferido (como hace
`provision/40_services.sh`) o por SSH.

## Puesta en marcha (una sola vez)

En **Settings › Secrets and variables › Actions** del repositorio:

| Secret | Valor |
|---|---|
| `PROETI_RENDEZVOUS_SERVER` | `support.proetisa.com` |
| `PROETI_RS_PUB_KEY` | la clave **pública** del servidor (`id_ed25519.pub` de hbbs) |
| `PROETI_PUSH_TOKEN` | token *fine-grained* con acceso **solo a este repo** y permisos *Contents: read and write* y *Workflows: read and write* |

`PROETI_PUSH_TOKEN` es necesario porque el token automático de Actions no puede
subir commits que contengan workflows, y lo que sube no dispara otros
workflows. Caduca: **renovarlo antes de que venza** o la sincronización
fallará (y abrirá el issue).

La clave del servidor es pública por diseño: la lleva cada cliente y cualquiera
puede sacarla de una máquina. Va en un secret solo para no dejarla escrita en
el repo. La **privada** no hace falta aquí y no debe estar nunca ni en el repo
ni en sus secrets. Lo que protege cada máquina es **su contraseña de
RustDesk**.

GitHub desactiva los workflows programados de un repo público tras **60 días
sin actividad** en la rama principal. Si ocurre, basta con reactivarlo en la
pestaña Actions.

## Licencia

AGPL-3.0, la misma de RustDesk ([LICENSE](LICENSE)). Por eso este repositorio
es público: quien reciba una máquina con PROETI Asistencia tiene derecho al
código, y está aquí, en la etiqueta de la versión que lleva. «RustDesk» y su
logo son marcas de sus autores. Aquí se han sustituido el logo y el nombre que
se ve en las ventanas, aunque aún quedan menciones sueltas en algunos textos
traducidos.
