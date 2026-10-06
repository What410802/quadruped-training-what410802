#!/bin/sh
# 激活 pixi 环境（default）时由 pixi source 本脚本（入口：仓库根 pixi.toml 的 [activation]）。
#
# 作用：把仓库里**所有已构建**的 colcon / ament 工作空间接进当前环境，省掉每个新终端手敲
# `source <工作空间>/install/setup.sh`。没构建过的（没有 install/）自动跳过，不报错。
#
# 为什么放在**仓库根** scripts/ 而不是某个任务目录里：根 pixi.toml 是仓库级文件，不该写任务级
# 路径（否则每加一个用到 ROS 的任务，都要回头改根文件、再加一个链接脚本）。这里改成**发现**：
# 扫 `@<任务目录>/**/install/setup.sh`，新增 ROS 任务只要照常 colcon build 就会被自动带上。
#
# 三种用法（什么时候还需要手动 source）与下面 IFS 写法的原理见 @20261005_ros2_example/docs/pixi-ros2.md §2.2。

# colcon / ament 生成的 setup.sh 假定变量已定义，而激活上下文可能开着 `set -u`：
# 先记下原状态、关掉，source 完再恢复。
case $- in
*u*) _ros2_ws_had_u=1 ;;
*) _ros2_ws_had_u=0 ;;
esac
set +u

_ros2_ws_root="${PIXI_PROJECT_ROOT:-}"
if [ -z "$_ros2_ws_root" ]; then
    echo "activate_ros2_workspaces.sh: PIXI_PROJECT_ROOT 未设置，跳过 source 工作空间 install/setup.sh" >&2
else
    # 找深度 ≤4 的 install/setup.sh（正好覆盖 @任务/install 与 @任务/<工作空间名>/install），
    # 跳过 .pixi 里的第三方东西；LC_ALL=C 排序，保证多个工作空间时的 source 顺序可预期
    # （同名包以**后** source 的为准）。
    _ros2_ws_list=$(LC_ALL=C find "$_ros2_ws_root" -maxdepth 4 -type f -path '*/install/setup.sh' \
        -not -path '*/.pixi/*' 2>/dev/null | LC_ALL=C sort)
    # 用换行当分隔符迭代：既不用管道（管道里 source 会落在子 shell、环境改动丢失），
    # 也不怕路径里有空格。
    _ros2_ws_ifs=$IFS
    IFS='
'
    for _ros2_ws_setup in $_ros2_ws_list; do
        if [ -f "$_ros2_ws_setup" ]; then
            . "$_ros2_ws_setup"
        fi
    done
    IFS=$_ros2_ws_ifs
fi

unset _ros2_ws_list _ros2_ws_setup _ros2_ws_root _ros2_ws_ifs
if [ "$_ros2_ws_had_u" = 1 ]; then
    set -u
fi
unset _ros2_ws_had_u
