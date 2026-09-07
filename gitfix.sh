#!/bin/sh
# Raeumt liegengebliebene git-.lock-Dateien weg - nur innerhalb von .git/.
#
# Hintergrund: auf diesem Mount ist rm gesperrt, mv aber erlaubt. Git legt bei
# jedem Commit .lock-Dateien an und raeumt sie normalerweise selbst weg; das
# schlaegt hier fehl. Die Reste blockieren den naechsten Befehl mit
# "Unable to create '.git/HEAD.lock': File exists". Also verschieben statt loeschen.
TRASH=".git/trash/$(date +%s)"
mkdir -p "$TRASH"
find .git -maxdepth 3 -name "*.lock" -exec mv {} "$TRASH/" \; 2>/dev/null
find .git/objects -name "tmp_obj_*" -exec mv {} "$TRASH/" \; 2>/dev/null
exit 0
