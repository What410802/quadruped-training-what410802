#!/usr/bin/env bash
# 实机命令的包装：**行缓冲**（`stdbuf -oL`）+ 自动按时间戳命名日志。
#
# 用法（需要 root 的命令把 `sudo` 写在**前面**）：
#   sudo @20260927_motor/scripts/run_log.sh s0 $P --port /dev/ttyUSB0
#   @20260927_motor/scripts/run_log.sh s2b pixi run python @20260927_motor/scripts/agent_scripts/analyse_watch_log.py /tmp/s2.log
#
# 为什么 sudo 放在外面、而不是包一个"会自动加 sudo"的 shell 函数：
#   ① `sudo` 只认可执行文件，**不能调用 shell 函数**（`sudo RUN …` 会报 command not found）；
#   ② 写在外面，"哪条命令要 root、哪条不要"一眼可见，也不会出现"函数内部偷偷 sudo"这种意外；
#   ③ 分析脚本、dry run 这些不需要 root 的命令用同一个包装，不必维护两套。
#
# 为什么需要 `stdbuf -oL`：接了管道（tee）之后 stdout 不再是终端，C 库会从"按行缓冲"变成"按块缓冲"
# （4 KB），终端要攒一大段才刷、还会从半行中间断开。详见 docs/pitfalls/environment.md 的
# 「管道（| tee）让程序输出变卡顿」一节。
#
# 日志位置：<任务目录>/output/terminal/motor-real-<YYYYMMDDHHmm>-<阶段>.txt
# （任务目录由本脚本位置推出，所以从任何工作目录调用都一样。）
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "用法：$0 <阶段> <命令…>" >&2
    echo "例：  sudo $0 s0 \$P --port /dev/ttyUSB0" >&2
    echo "      $0 s2b pixi run python @20260927_motor/scripts/agent_scripts/analyse_watch_log.py /tmp/s2.log" >&2
    exit 2
fi

phase="$1"
shift

task_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_dir="$task_dir/output/terminal"
mkdir -p "$log_dir"
log="$log_dir/motor-real-$(date +%Y%m%d%H%M)-$phase.txt"

{
    echo "# $(date '+%F %T')  命令：$*"
    echo "# 由 scripts/run_log.sh 记录（行缓冲；日志：$log）"
} >>"$log"
echo "日志 → $log" >&2

# 行缓冲跑命令，stdout/stderr 同时进终端与日志；stdin 保持原样（交互式程序照常读键盘）
stdbuf -oL "$@" 2>&1 | tee -a "$log"
exit "${PIPESTATUS[0]}"
