#!/usr/bin/env bash
# Check that the archived rl_sar assignment stack is still buildable/runnable as
# the P2 fallback. Runs the two hardware-free self-tests only; the full walk test
# needs the simulation GUI and is documented separately.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

BEST="@20261007_assignment/ws/src/rl_sar/policy/black/himloco/best.pt"
test -f "$BEST"

pixi run bash -lc '
  set -eo pipefail
  set +u
  source @20261005_ros2/ws/install/setup.bash
  source @20261007_assignment/ws/install/setup.bash
  ros2 run rl_sar input_map_selftest >/tmp/rl_sar_input_map.log
  ros2 run rl_sar command_limit_selftest >/tmp/rl_sar_command_limit.log
  tail -1 /tmp/rl_sar_input_map.log
  tail -1 /tmp/rl_sar_command_limit.log
'
echo "rl_sar fallback self-tests: OK"
