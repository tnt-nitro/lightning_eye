#!/bin/bash
# Lightning Eye launcher — waits for desktop, logs output, starts app.
INSTALL_DIR="${HOME}/lightning_eye"
LOG_DIR="${INSTALL_DIR}/logs"
LOG_FILE="${LOG_DIR}/startup.log"
PYTHON="${INSTALL_DIR}/.venv/bin/python"

mkdir -p "${LOG_DIR}"
exec >>"${LOG_FILE}" 2>&1
echo "========== $(date -Iseconds) =========="

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-${HOME}/.Xauthority}"
export GPIOZERO_PIN_FACTORY="${GPIOZERO_PIN_FACTORY:-lgpio}"

# Stop stale instance (crashed runs block HTTP port / GPIO)
pkill -f "[.]venv/bin/python -m app.run" 2>/dev/null || true
sleep 1

# Wait up to 2 minutes for X/Wayland session
for i in $(seq 1 60); do
    if command -v xdpyinfo >/dev/null 2>&1 && xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
        echo "Display ${DISPLAY} ready after ${i} attempts"
        break
    fi
    echo "Waiting for display (${i}/60)..."
    sleep 2
done

cd "${INSTALL_DIR}" || exit 1

if [[ ! -x "${PYTHON}" ]]; then
    echo "ERROR: Python venv not found at ${PYTHON}"
    exit 1
fi

echo "Starting Lightning Eye..."
exec "${PYTHON}" -m app.run
