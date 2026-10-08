//! PROETI Asistencia: la sesión y su chat, para la interfaz del equipo.
//!
//! El gestor de conexión (`rustdesk --cm`) es el único proceso que sabe en cada
//! momento quién hay dentro. En PROETI su ventana no se enseña nunca (ver
//! `hide_cm` en scripts/aplicar_branding.py): la sesión la enseña la cabecera de
//! la interfaz del equipo, y el chat un panel a la derecha. Los dos leen lo que
//! se escribe aquí, en `/run/proeti-asistencia`:
//!
//! - `estado.json`: quién está conectado. Se reescribe al entrar o salir una
//!   conexión.
//! - `chat.json`: los últimos mensajes, de los dos lados.
//! - `salida/*.json`: lo que escribe el equipo. Lo deja la interfaz (www-data) y
//!   un hilo de aquí lo manda al técnico y lo borra.
//!
//! La carpeta la crea `provision/63_asistencia.sh` con tmpfiles.d: es del
//! usuario del kiosko (con quien corre `--cm`) y la lee www-data; `salida/` es
//! del grupo www-data, para que la interfaz pueda dejar mensajes. Si no existe,
//! no se escribe nada y RustDesk funciona igual.
//!
//! Este fichero lo copia `aplicar_branding.py` al árbol de RustDesk; no es suyo.
#![cfg_attr(not(target_os = "linux"), allow(dead_code))]

use crate::ui_cm_interface::Client;
use hbb_common::log;
use std::collections::HashMap;
use std::sync::{Mutex, Once};
use std::time::{SystemTime, UNIX_EPOCH};

const CARPETA: &str = "/run/proeti-asistencia";
const ESTADO: &str = "estado.json";
const CHAT: &str = "chat.json";
const SALIDA: &str = "salida";
/// Mensajes que se guardan en `chat.json` (los más antiguos se caen).
const MAX_MENSAJES: usize = 200;
/// Caracteres por mensaje: el panel del kiosko no es para pegar un fichero.
const MAX_TEXTO: usize = 2000;
/// Cada cuánto mira el hilo si la interfaz ha dejado algo que mandar.
const SALIDA_CADA_MS: u64 = 500;

/// Cuándo se vio por primera vez cada conexión (id de conexión, epoch en s).
/// RustDesk no guarda la hora de entrada y la cabecera la necesita.
static INICIOS: Mutex<Vec<(i32, u64)>> = Mutex::new(Vec::new());
/// Copia de las conexiones vivas, para el chat: quién escribe y a quién se manda.
static CONEXIONES: Mutex<Vec<Conexion>> = Mutex::new(Vec::new());
static CHAT_LOG: Mutex<Chat> = Mutex::new(Chat { n: 0, mensajes: Vec::new() });
static HILO_SALIDA: Once = Once::new();

#[derive(Clone)]
struct Conexion {
    id: i32,
    tecnico: String,
    nombre: String,
    tipo: &'static str,
    aceptada: bool,
}

struct Chat {
    n: u64,
    mensajes: Vec<serde_json::Value>,
}

/// Se llama cada vez que entra o sale una conexión, con la lista ya cambiada.
pub fn publicar(clientes: &HashMap<i32, Client>) {
    if let Ok(mut c) = CONEXIONES.lock() {
        *c = clientes
            .iter()
            .filter(|(_, c)| !c.disconnected)
            .map(|(id, c)| Conexion {
                id: *id,
                tecnico: c.peer_id.clone(),
                nombre: c.name.clone(),
                tipo: tipo(c),
                aceptada: c.authorized,
            })
            .collect();
    }
    let texto = match INICIOS.lock() {
        Ok(mut inicios) => estado_json(clientes, &mut inicios, ahora(), std::process::id()),
        Err(_) => return,
    };
    #[cfg(target_os = "linux")]
    {
        escribir(std::path::Path::new(CARPETA), ESTADO, &texto);
        HILO_SALIDA.call_once(|| {
            std::thread::spawn(vigilar_salida);
        });
    }
    #[cfg(not(target_os = "linux"))]
    let _ = texto;
}

/// Un mensaje de chat del técnico (conexión `id`).
pub fn chat_entrante(id: i32, texto: &str) {
    let con = CONEXIONES
        .lock()
        .ok()
        .and_then(|c| c.iter().find(|c| c.id == id).cloned());
    let (tecnico, nombre) = con.map(|c| (c.tecnico, c.nombre)).unwrap_or_default();
    apuntar("tecnico", id, &tecnico, &nombre, texto, "");
}

/// Mete un mensaje en el registro del chat y reescribe `chat.json`.
fn apuntar(de: &str, conexion: i32, tecnico: &str, nombre: &str, texto: &str, marca: &str) {
    let texto: String = texto.chars().take(MAX_TEXTO).collect();
    if texto.trim().is_empty() {
        return;
    }
    let json = match CHAT_LOG.lock() {
        Ok(mut chat) => {
            chat.n += 1;
            let n = chat.n;
            chat.mensajes.push(serde_json::json!({
                "n": n,
                "t": ahora(),
                "de": de,
                "conexion": conexion,
                "tecnico": tecnico,
                "nombre": nombre,
                "texto": texto,
                "marca": marca,
            }));
            if chat.mensajes.len() > MAX_MENSAJES {
                let sobran = chat.mensajes.len() - MAX_MENSAJES;
                chat.mensajes.drain(..sobran);
            }
            serde_json::json!({
                "v": 1,
                "pid": std::process::id(),
                "mensajes": chat.mensajes,
            })
            .to_string()
        }
        Err(_) => return,
    };
    #[cfg(target_os = "linux")]
    escribir(std::path::Path::new(CARPETA), CHAT, &json);
    #[cfg(not(target_os = "linux"))]
    let _ = json;
}

/// Lo que ha escrito el equipo, en orden. Cada fichero lo deja la interfaz con
/// un nombre que ordena por tiempo, y se borra al leerlo (se mande o no).
#[cfg(target_os = "linux")]
fn vigilar_salida() {
    let dir = std::path::Path::new(CARPETA).join(SALIDA);
    loop {
        std::thread::sleep(std::time::Duration::from_millis(SALIDA_CADA_MS));
        let mut ficheros: Vec<std::path::PathBuf> = match std::fs::read_dir(&dir) {
            Ok(rd) => rd
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.extension().map_or(false, |x| x == "json"))
                .collect(),
            Err(_) => continue,
        };
        ficheros.sort();
        for f in ficheros {
            let contenido = std::fs::read_to_string(&f).unwrap_or_default();
            if let Err(e) = std::fs::remove_file(&f) {
                // Si no se puede borrar, se mandaría una y otra vez: mejor no mandarlo.
                log::warn!("PROETI Asistencia: no se pudo borrar {}: {}", f.display(), e);
                continue;
            }
            let v: serde_json::Value = match serde_json::from_str(&contenido) {
                Ok(v) => v,
                Err(_) => continue,
            };
            let texto = v["texto"].as_str().unwrap_or_default();
            let marca: String = v["marca"]
                .as_str()
                .unwrap_or_default()
                .chars()
                .filter(|c| c.is_ascii_lowercase())
                .take(16)
                .collect();
            enviar(texto, &marca);
        }
    }
}

/// Manda un mensaje del equipo a las conexiones que tienen chat (las que ven la
/// pantalla o los archivos; un túnel no tiene dónde enseñarlo).
fn enviar(texto: &str, marca: &str) {
    let texto: String = texto.chars().take(MAX_TEXTO).collect();
    if texto.trim().is_empty() {
        return;
    }
    let destinos: Vec<i32> = CONEXIONES
        .lock()
        .map(|c| {
            c.iter()
                .filter(|c| c.aceptada && matches!(c.tipo, "pantalla" | "archivos" | "camara"))
                .map(|c| c.id)
                .collect()
        })
        .unwrap_or_default();
    if destinos.is_empty() {
        return;
    }
    for id in &destinos {
        crate::ui_cm_interface::send_chat(*id, texto.clone());
    }
    apuntar("equipo", destinos[0], "", "", &texto, marca);
}

fn ahora() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Qué está haciendo la conexión. Un túnel (los despliegues por SSH) no ve la
/// pantalla, y la cabecera lo enseña distinto.
fn tipo(c: &Client) -> &'static str {
    if !c.port_forward.is_empty() {
        "tunel"
    } else if c.is_terminal {
        "terminal"
    } else if c.is_file_transfer {
        "archivos"
    } else if c.is_view_camera {
        "camara"
    } else {
        "pantalla"
    }
}

/// El JSON de `estado.json`. `pid` es el del proceso `--cm`: quien lo lee
/// comprueba que sigue vivo, porque si el gestor se cae no llega a escribir la
/// salida.
fn estado_json(
    clientes: &HashMap<i32, Client>,
    inicios: &mut Vec<(i32, u64)>,
    t: u64,
    pid: u32,
) -> String {
    // Una conexión cerrada se queda en la lista marcada `disconnected` (la ventana
    // de RustDesk la enseña tachada); aquí ya no cuenta.
    let mut ids: Vec<i32> = clientes
        .iter()
        .filter(|(_, c)| !c.disconnected)
        .map(|(id, _)| *id)
        .collect();
    ids.sort_unstable();
    inicios.retain(|(id, _)| ids.contains(id));

    let mut sesiones = Vec::with_capacity(ids.len());
    for id in ids {
        let c = &clientes[&id];
        let desde = match inicios.iter().find(|(i, _)| *i == id) {
            Some((_, d)) => *d,
            None => {
                inicios.push((id, t));
                t
            }
        };
        sesiones.push(serde_json::json!({
            "conexion": id,
            "tecnico": c.peer_id,
            "nombre": c.name,
            "tipo": tipo(c),
            "autorizada": c.authorized,
            "desde": desde,
            "teclado": c.keyboard,
            "portapapeles": c.clipboard,
            "archivos": c.file,
            "audio": c.audio,
            "grabando": c.recording,
            "bloqueo_entrada": c.block_input,
        }));
    }
    serde_json::json!({
        "v": 1,
        "pid": pid,
        "actualizado": t,
        "sesiones": sesiones,
    })
    .to_string()
}

/// Escritura atómica (temporal + rename): quien lee nunca ve el fichero a medias.
#[cfg(target_os = "linux")]
fn escribir(carpeta: &std::path::Path, nombre: &str, texto: &str) {
    use std::os::unix::fs::PermissionsExt;
    if !carpeta.is_dir() {
        return;
    }
    let tmp = carpeta.join(format!(".{}.{}.tmp", nombre, std::process::id()));
    let fin = carpeta.join(nombre);
    let r = (|| -> std::io::Result<()> {
        std::fs::write(&tmp, texto)?;
        std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o644))?;
        std::fs::rename(&tmp, &fin)
    })();
    if let Err(e) = r {
        let _ = std::fs::remove_file(&tmp);
        log::warn!("PROETI Asistencia: no se pudo escribir {}: {}", fin.display(), e);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_con_y_sin_conexiones() {
        let mut inicios = Vec::new();
        let vacio = estado_json(&HashMap::new(), &mut inicios, 100, 7);
        let v: serde_json::Value = serde_json::from_str(&vacio).unwrap();
        assert_eq!(v["pid"], 7);
        assert_eq!(v["sesiones"].as_array().unwrap().len(), 0);
    }
}
