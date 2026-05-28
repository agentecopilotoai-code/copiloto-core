"""SEC-009.1-FU: backup verifier sin docker socket.

Antes el verifier exigía `docker info` para correr Layer 2 (Postgres
efímero); hosts rootless / managed runners caían al degraded
`pg_restore --list`. Fix: detectar runtime preferido — `docker` con
daemon respondiendo PRIMERO (mantiene compose actual), `podman` (rootless)
como fallback. Si ninguno funciona, queda el degraded mode.

Defenders del fix:
- `CONTAINER_CMD` variable elegida por preferencia docker>podman.
- Todas las invocaciones literales `docker ...` reemplazadas por
  `"$CONTAINER_CMD" ...`.
- `EN_DOCKER` detection extendida con `/run/.containerenv` (podman /
  runc) además de `/.dockerenv`.
- `RESTORE_MODE` lleva sufijo `:docker` / `:podman` para auditoría.
- Gate de Layer 2 chequea `-n "$CONTAINER_CMD"` (no `command -v docker`).
"""
from __future__ import annotations

from pathlib import Path


SCRIPT = Path('copiloto_core/scripts/verify-backup.sh')


def test_sec_009_1_fu_container_cmd_variable_detects_runtime():
    src = SCRIPT.read_text()
    # Debe existir una variable CONTAINER_CMD que se selecciona por preferencia.
    assert 'CONTAINER_CMD=""' in src, (
        "SEC-009.1-FU: debe existir `CONTAINER_CMD=\"\"` inicializado antes "
        "de la selección de runtime."
    )
    # Preferencia: docker > podman.
    assert 'command -v docker' in src and 'docker info' in src, (
        "SEC-009.1-FU: la detección debe probar `docker info` para confirmar "
        "que el daemon responde (no basta con `command -v`)."
    )
    assert 'command -v podman' in src and 'podman info' in src, (
        "SEC-009.1-FU: la detección debe probar `podman info` como fallback "
        "cuando docker no está o su daemon no responde."
    )
    # Docker debe evaluarse PRIMERO (mantiene compose actual sin sorpresas).
    docker_idx = src.find('command -v docker >/dev/null 2>&1 && docker info')
    podman_idx = src.find('command -v podman >/dev/null 2>&1 && podman info')
    assert docker_idx > 0 and podman_idx > 0 and docker_idx < podman_idx, (
        "SEC-009.1-FU: la rama `docker` debe evaluarse antes que `podman` "
        "para no romper deploys actuales con docker daemon disponible."
    )


def test_sec_009_1_fu_en_docker_detection_also_recognizes_podman_containers():
    src = SCRIPT.read_text()
    assert '-f /.dockerenv' in src, (
        "SEC-009.1-FU: el chequeo de docker (`/.dockerenv`) debe preservarse."
    )
    assert '-f /run/.containerenv' in src, (
        "SEC-009.1-FU: además debe detectar `/run/.containerenv` (podman / "
        "runc) para que el worker reconozca que está corriendo bajo un "
        "container rootless y use la lógica EN_DOCKER=1."
    )


def test_sec_009_1_fu_no_literal_docker_run_commands_left():
    """Si alguien re-introduce `docker run` / `docker network` literal, el
    podman fallback se rompe (solo aplica al wrapper, no a docker hardcoded).
    """
    src = SCRIPT.read_text()
    # Los comandos operativos deben usar la variable. Excluimos comentarios:
    # filtramos líneas que empiezan con `#`.
    code_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.strip().startswith('#')
    ]
    code_only = '\n'.join(code_lines)
    # Patterns prohibidos en líneas de código (no comentarios).
    for forbidden in (
        'docker run ',
        'docker network create',
        'docker network rm',
        'docker network connect',
        'docker network disconnect',
        'docker rm -f',
    ):
        assert forbidden not in code_only, (
            f'SEC-009.1-FU regresión: `{forbidden}` literal volvió al código. '
            'Debe usar `"$CONTAINER_CMD" ...` para soportar podman fallback.'
        )


def test_sec_009_1_fu_layer_2_gate_uses_container_cmd_var():
    src = SCRIPT.read_text()
    # El gate principal de Layer 2 debe testear que CONTAINER_CMD esté seteada.
    assert '[[ -n "$CONTAINER_CMD" ]]' in src, (
        "SEC-009.1-FU: el gate principal de Layer 2 debe ser "
        "`[[ -n \"$CONTAINER_CMD\" ]]`, no `command -v docker` hardcoded."
    )


def test_sec_009_1_fu_restore_mode_includes_runtime_suffix():
    src = SCRIPT.read_text()
    # El RESTORE_MODE en el path ephemeral debe llevar el sufijo del runtime.
    assert 'RESTORE_MODE="ephemeral_isolated:${CONTAINER_CMD}"' in src, (
        "SEC-009.1-FU: `RESTORE_MODE` en la rama ephemeral debe ser "
        "`ephemeral_isolated:${CONTAINER_CMD}` para que el audit log "
        "distinga si el restore corrió bajo docker o podman."
    )
    # El comparador del sanity branch debe ser prefix-match.
    assert '[[ "$RESTORE_MODE" == ephemeral_isolated* ]]' in src, (
        "SEC-009.1-FU: el branch de sanity checks debe comparar por prefijo "
        "(`ephemeral_isolated*`) porque el sufijo `:docker`/`:podman` cambia."
    )


def test_sec_009_1_fu_degraded_mode_message_mentions_both_runtimes():
    src = SCRIPT.read_text()
    assert 'Ni docker ni podman disponibles' in src, (
        "SEC-009.1-FU: el mensaje del degraded mode debe aclarar que NI "
        "docker NI podman están disponibles (sino el operador asume que "
        "es solo docker y no prueba podman)."
    )
