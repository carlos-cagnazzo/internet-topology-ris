#!/usr/bin/env bash
# Full day without updates
set -euo pipefail
#

export D="20250401"

just date=$D collectors=rrc00-rrc25 download
just date=$D download-routeviews
just date=$D process
just date=$D topology
