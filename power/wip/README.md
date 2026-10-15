# Superseded

Replaced by `power/12-store-hold.patch` (kernel r5). Kept for reference only; do not build.

# Unaccepted battery-policy work

Do not build or deploy patch12. It is excluded from the kernel APKBUILD.
The C harness compiles but intentionally exposes an unresolved failing protection case:
CHARGE_DISABLE rewrites a charging request before the new cap guard and may overwrite
BUCK_OFF. Complete guard ordering, all protection/recovery paths and factory-mode
review before integration. The companion UI patch is also unapplied.

User goal: 70% cap on USB and Qi; prefer USB when both present; external power
should carry the load at the cap. A cap does not prove battery isolation or zero
battery current. Current deployed kernel retains the original Samsung store policy.
