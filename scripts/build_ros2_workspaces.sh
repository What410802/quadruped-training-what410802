#!/bin/sh
# 编译仓库里**所有** colcon 工作空间（自动发现）。
#
# 为什么是"发现"而不是在根 pixi.toml 里列三个任务目录：根 pixi.toml 是仓库级文件，写进
# "@20261005_ros2/ws" 这类任务级路径就等于把任务清单钉在根文件上，每加一个 ROS 任务都要回来改。
# 这里按 colcon 的约定找：某目录下有 src/，且 src 下一层能找到 package.xml。
# 新增 ROS 任务只要照常建包，本脚本与 `pixi run ros2-build` 都会自动带上它。
#
# 只想编一个工作空间时不用这个脚本：`cd <工作空间> && pixi run colcon build --symlink-install`
# （pixi 会从当前目录往上找仓库根的 pixi.toml，不必传 --manifest-path；在仓库**之外**才需要）。
#
# 关于下面的 IFS 写法（与 scripts/activate_ros2_workspaces.sh 同一套）：
#   1) 命令替换 `$(find …)` 的结果默认按 IFS（空格/制表/换行）拆词，而路径里可能带空格；
#      把 IFS 单独设成"只有换行"，就只按行拆、不会把一个路径拆成两半。
#   2) 不能用 `find … | while read …` 的管道写法：管道两端各在**子 shell** 里跑，
#      循环里 cd 出来的工作目录、export 的环境变量出了循环就没了（本脚本靠 subshell 包住
#      colcon，反而必须让"cd"只影响那一轮）。所以这里用变量 + 换行 IFS 迭代，循环留在本 shell。
set -e

_root=${PIXI_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}

_ws_list=$(LC_ALL=C find "$_root" -maxdepth 4 -type d -name src \
    -not -path '*/.pixi/*' -not -path '*/build/*' -not -path '*/install/*' 2>/dev/null | LC_ALL=C sort)

_ifs_saved=$IFS
IFS='
'
_n=0
for _src in $_ws_list; do
    _ws=${_src%/src}
    # src/ 下真要有包才算工作空间（空 src/ 不算）
    if [ -z "$(find "$_ws/src" -maxdepth 2 -name package.xml -print -quit 2>/dev/null)" ]; then
        continue
    fi
    printf '==> colcon build --symlink-install    %s\n' "${_ws#"$_root"/}"
    (cd "$_ws" && colcon build --symlink-install)
    _n=$((_n + 1))
done
IFS=$_ifs_saved

if [ "$_n" -eq 0 ]; then
    echo "没找到 colcon 工作空间（约定：<任务目录>/**/src/<包>/package.xml）" >&2
    exit 1
fi
printf '==> 共编译 %d 个工作空间\n' "$_n"
