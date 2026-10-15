# interactive bash: prompt stack mirrored from the desktop (starship + ble.sh + fzf)
[ -f /etc/bash/bashrc ] && . /etc/bash/bashrc
for f in ~/.bashrc.d/*.sh; do
	# the phone screen Terminal (display.py, TERM=linux) is too small/slow for ble.sh
	[ "$TERM" = linux ] && [ "${f##*/}" = blesh.sh ] && continue
	[ -r "$f" ] && . "$f"
done
