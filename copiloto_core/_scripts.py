"""Dispatcher de scripts bash empaquetados (v1.3.0).

# Por qué un dispatcher

A partir de v1.3.0, el core ships 8 scripts operacionales útiles
para cualquier deployment (generar secrets, configurar Auth0,
backups, restore, smoke-test, reset local). El consumer NO los ve
en su filesystem — los invoca via subcomando CLI:

    python -m copiloto_core generate-secrets
    python -m copiloto_core auth0-configure
    python -m copiloto_core backup-local
    ...

Internamente cada subcomando resuelve la ruta del .sh dentro del
package via `importlib.resources` y lo ejecuta vía subprocess.
Args extra después del subcomando se pasan tal cual al script.

# Por qué no portar todo a Python

`configure-auth0.sh` solo tiene 1558 líneas de bash bien probado
(2 audits cerrados + ~40 tests estáticos). Reescribirlo en Python
sería semanas de trabajo + nuevo perímetro de bugs. El dispatcher
deja el código operacional EN bash (donde funciona y está probado)
y solo agrega la fachada Python.

# Cuándo NO usar subprocess

Si el script invocado necesita el cwd del PROYECTO consumer (no
el cwd del package del core), pasamos `cwd=Path.cwd()` explícito.
Cualquier script que escriba en `./backups/`, `./.env`, `./.secrets/`
necesita esto. Los 8 scripts shippeados siguen esa convención.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from importlib import resources
from pathlib import Path


logger = logging.getLogger(__name__)


class ScriptError(Exception):
    """Fallo al invocar un script empaquetado."""


def _resolve_script_path(script_name: str) -> Path:
    """Resuelve el path filesystem de `copiloto_core/scripts/<name>`.

    Usa `importlib.resources` para que funcione tanto cuando el core
    está instalado como wheel (pip), editable (-e), o desde source.

    Args:
      script_name: nombre del archivo dentro de `copiloto_core/scripts/`
        (ej. `'generate-local-secrets.sh'`).

    Returns:
      `Path` absoluto al script.

    Raises:
      ScriptError: si el script no existe en el package.
    """
    try:
        ref = resources.files('copiloto_core.scripts').joinpath(script_name)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise ScriptError(
            f'No se pudo resolver copiloto_core.scripts/{script_name}: {exc}',
        ) from exc
    if not ref.is_file():
        raise ScriptError(
            f'Script no encontrado en el package: {script_name}. '
            f'Verificá que copiloto-core esté instalado completamente '
            f'(los .sh viajan como package-data).',
        )
    return Path(str(ref))


def run_packaged_script(
    script_name: str,
    args: list[str] | None = None,
    *,
    cwd: Path | None = None,
) -> int:
    """Ejecuta un script bash empaquetado vía subprocess.

    El stdout/stderr del script SE PROPAGAN al terminal del usuario
    (no los capturamos) — eso es lo que quiere el operador interactivo
    para ver el progreso de un backup o de la configuración Auth0.

    Args:
      script_name: nombre del archivo (`'configure-auth0.sh'`, etc.).
      args: argumentos pass-through al script.
      cwd: directorio de trabajo. Default: cwd del proceso Python
        (el del CONSUMER, no el del package). Esto es lo que quiere
        cualquier script que lea `./.env` o escriba `./backups/`.

    Returns:
      Exit code del script. 0 = éxito.

    Raises:
      ScriptError: si bash no está disponible o el script no existe.
    """
    if shutil.which('bash') is None:
        raise ScriptError(
            'No se encontró `bash` en PATH. Los scripts del core requieren '
            'bash 4.x+. En macOS instalalo con `brew install bash`.',
        )

    script_path = _resolve_script_path(script_name)
    if cwd is None:
        cwd = Path.cwd()

    cmd = ['bash', str(script_path), *(args or [])]
    logger.info('run_packaged_script script=%s args=%s cwd=%s',
                script_name, args, cwd)
    # No pasamos stdin/stdout/stderr explícitos — subprocess hereda
    # los del padre por default, lo que es exactamente lo que queremos:
    # output del bash va al terminal del user, input interactivo
    # funciona. Pasar `sys.stdin` explícito rompe en pytest (los
    # buffers de capture no son file descriptors reales).
    try:
        completed = subprocess.run(  # noqa: S603 (script path resolved + bash whitelisted)
            cmd,
            cwd=str(cwd),
            check=False,
        )
    except FileNotFoundError as exc:
        raise ScriptError(
            f'Fallo al lanzar bash: {exc}. '
            f'¿Está bash en PATH?',
        ) from exc
    return completed.returncode


__all__ = [
    'ScriptError',
    'run_packaged_script',
]
