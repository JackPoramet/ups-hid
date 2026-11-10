#!/bin/bash
# Color only interactive terminals; keep redirected output and NO_COLOR plain.
ui_emit() {
    local fd="$1" color="$2" label="$3" message="$4"
    if [ -t "$fd" ] && [ -z "${NO_COLOR+x}" ] && [ "${TERM:-dumb}" != dumb ]; then
        printf '\033[%sm[%s] %s\033[0m\n' "$color" "$label" "$message" >&"$fd"
    else
        printf '[%s] %s\n' "$label" "$message" >&"$fd"
    fi
}
ui_info()  { ui_emit 1 36 INFO  "$1"; }
ui_ok()    { ui_emit 1 32 OK    "$1"; }
ui_warn()  { ui_emit 1 33 WARN  "$1"; }
ui_error() { ui_emit 2 31 ERROR "$1"; }
