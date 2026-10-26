#!/usr/bin/env bash
# HIM row0 (easiest official tier) mixed training + strict low-tier gate.
# Intended to be submitted to task-spooler as one serial full-GPU job.
set -uo pipefail

REPO="$HOME/rc_work/nwwolf_mjlab_training_release"
JOB="him_row0_mixed_gate_$(date +%m%d_%H%M)"
LOGDIR="$HOME/rc_work/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$JOB.log"
SUM="$LOGDIR/${JOB}_summary.txt"
FLAG="$HOME/5060ti_machine_use_flag.txt"
GATE="$HOME/rc_work/him_part2_gate.py"
export PATH="$HOME/.local/bin:$PATH"
export MUJOCO_GL=egl
export BLACKW_OFFICIAL_WARMSTART=/tmp/official_blackw_obstacle.pt
export BLACKW_MAX_ROW=0
export BLACKW_REWARD_CLIP=50
exec > >(tee -a "$LOG") 2>&1
cd "$REPO" || exit 1

RC=0
on_exit() { printf 0 > "$FLAG"; echo "[$JOB] end $(date -Is) rc=$RC" >> "$LOG"; }
trap on_exit EXIT
echo "[$JOB] start $(date -Is)"; : > "$SUM"
exec 9>/tmp/gpu.lock
flock -w 900 9 || { echo "[$JOB] gpu lock timeout"; RC=3; exit 3; }
for _ in $(seq 1 90); do
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')
  [ "${used:-99999}" -lt 1500 ] && break
  echo "[$JOB] wait gpu used=${used} MiB"; sleep 10
done
printf 1 > "$FLAG"
echo "train $(date -Is)" | tee -a "$SUM"
env BLACKW_OFFICIAL_WARMSTART=/tmp/official_blackw_obstacle.pt BLACKW_MAX_ROW=0 \
  .venv/bin/train blackw-official-him \
    --env.scene.num-envs 512 \
    --agent.num-steps-per-env 96 \
    --agent.max-iterations 1500 \
    --agent.save-interval 50 \
    --agent.algorithm.learning-rate 5e-4 \
    --agent.algorithm.entropy-coef 3e-3 \
    --agent.run-name "$JOB" \
    --agent.logger tensorboard
RC=$?
echo "train rc=$RC" | tee -a "$SUM"

RUN_DIR=$(ls -dt logs/rsl_rl/blackw_velocity_him/*_"$JOB" 2>/dev/null | head -1)
CKPT=""
if [ -n "$RUN_DIR" ]; then
  CKPT=$(ls -v "$RUN_DIR"/model_*.pt 2>/dev/null | tail -1)
fi
echo "run=$RUN_DIR ckpt=$CKPT" | tee -a "$SUM"

if [ -n "$CKPT" ] && [ -f "$GATE" ]; then
  for cat in platform slope stairs high_wall trench; do
    out="$LOGDIR/gate_${JOB}_${cat}.json"
    .venv/bin/python "$GATE" \
      --task blackw-official-him --checkpoint "$CKPT" \
      --category "$cat" --row 0 --attempts 20 --num-envs 8 \
      --vx-min 0.25 --vx-max 1.0 --vy 0.15 --wz 0.2 \
      --max-steps 1000 --out "$out" >/dev/null 2>&1
    rc=$?
    tail -n 1 "$SUM" >/dev/null
    printf "gate %s rc=%s " "$cat" "$rc" | tee -a "$SUM"
    [ -f "$out" ] && grep -oE '"success": [0-9]+|"failure": [0-9]+|"attempts_done": [0-9]+' "$out" | tr '\n' ' ' | tee -a "$SUM"
    echo | tee -a "$SUM"
  done
else
  echo "no checkpoint/gate; skip gate" | tee -a "$SUM"
fi
echo "$JOB done $(date -Is)" | tee -a "$SUM"
exit "$RC"
