#!/usr/bin/env bash
# Re-gate every checkpoint of the bad HIM row0 job with the corrected strict
# training-config gate (play=False, part2 terms asserted, clean obs, timeout).
set -uo pipefail
REPO="$HOME/rc_work/nwwolf_mjlab_training_release"
GATE="$HOME/rc_work/him_part2_gate.py"
RUN_DIR=$(ls -dt "$REPO"/logs/rsl_rl/blackw_velocity_him/*_him_row0_mixed_gate_* 2>/dev/null | head -1)
JOB="him_regate_job12_$(date +%m%d_%H%M)"
LOGDIR="$HOME/rc_work/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/$JOB.log"; SUM="$LOGDIR/${JOB}_summary.txt"
export PATH="$HOME/.local/bin:$PATH"; export MUJOCO_GL=egl
exec > >(tee -a "$LOG") 2>&1
cd "$REPO" || exit 1
on_signal() {
  printf 0 > "$HOME/5060ti_machine_use_flag.txt"
  echo "signal $1 $(date -Is)" >> "$LOG"
  exit "$1"
}
trap 'echo 0 > "$HOME/5060ti_machine_use_flag.txt"' EXIT
trap 'on_signal TERM' TERM
trap 'on_signal INT' INT
: > "$SUM"
echo "[$JOB] run_dir=$RUN_DIR start=$(date -Is)"
if [ -z "$RUN_DIR" ] || [ ! -f "$GATE" ]; then
  echo "missing run_dir or gate" | tee -a "$SUM"; exit 2
fi
printf 1 > "$HOME/5060ti_machine_use_flag.txt"
exec 9>/tmp/gpu.lock
flock -w 900 9 || exit 3
for _ in $(seq 1 90); do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')
  [ "${used:-99999}" -lt 1500 ] && break
  sleep 10
done
for ck in "$RUN_DIR"/model_*.pt; do
  name=$(basename "$ck" .pt)
  for cat in platform slope stairs high_wall trench; do
    out="$LOGDIR/${JOB}_${name}_${cat}.json"
    .venv/bin/python "$GATE" \
      --task blackw-official-him --checkpoint "$ck" \
      --category "$cat" --row 0 --attempts 10 --num-envs 8 \
      --vx-min 0.25 --vx-max 1.0 --vy 0.15 --wz 0.2 \
      --max-steps 1000 --out "$out" >/dev/null 2>&1
    rc=$?
    printf "gate %s %s rc=%s " "$name" "$cat" "$rc" | tee -a "$SUM"
    [ -f "$out" ] && grep -oE '"success": [0-9]+|"failure": [0-9]+|"attempts_done": [0-9]+|"gate_pass": (true|false)' "$out" | tr '\n' ' ' | tee -a "$SUM"
    echo | tee -a "$SUM"
  done
done
echo "$JOB done $(date -Is)" | tee -a "$SUM"
