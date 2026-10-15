# interactive bash: prompt stack mirrored from the desktop (starship + ble.sh + fzf)
[ -f /etc/bash/bashrc ] && . /etc/bash/bashrc
# the phone's kernel console (/dev/ttyN) is too slow for ble.sh and its font has no Nerd Font icons;
# the dashboard's Terminal tab runs on a pty and keeps them
case $(tty) in /dev/tty[0-9]*) vt=1;; *) vt=;; esac
for f in ~/.bashrc.d/*.sh; do
	[ -n "$vt" ] && case ${f##*/} in blesh.sh|starship.sh) continue;; esac
	[ -r "$f" ] && . "$f"
done
[ -n "$vt" ] && PS1='\[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]\$ '
