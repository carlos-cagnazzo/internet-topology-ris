#!/usr/bin/env bash
set -euo pipefail

D="20250427"

# Run ris-day one collector at a time so update files are downloaded,
# processed, and deleted before the next collector starts.
for C in rrc00 rrc01 rrc02 rrc03 rrc04 rrc05 rrc06 rrc07 rrc10 rrc11 \
         rrc12 rrc13 rrc14 rrc15 rrc16 rrc18 rrc19 rrc20 rrc21 rrc22 \
         rrc23 rrc24 rrc25; do
    just date=$D collectors=$C ris-day
done

just date=$D download-routeviews
just date=$D process
just date=$D topology
