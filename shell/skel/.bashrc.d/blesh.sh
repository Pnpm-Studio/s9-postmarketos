# ble.sh: Bash line editor, syntax highlighting, and menus.
# Loaded before fzf.sh by the .bashrc.d alphabetical order. The image ships it in /usr/share/blesh.
if [[ $- == *i* ]]; then
    for b in "$HOME/.local/share/blesh/ble.sh" /usr/share/blesh/ble.sh; do
        [[ -r $b ]] && { source "$b"; break; }
    done
fi
