#!/bin/sh
# 一次性权限配置：让**当前用户**能用仿真手柄（写 /dev/uinput）与手柄节点（读 /dev/input/event*）。
#
# 用法（需要 sudo，本仓库唯一的特权操作）：
#
#     sudo @20261005_ros2/scripts/setup_joy_devices.sh
#
# 做的事：
#   1. modprobe uinput（没有内建时加载内核模块，/dev/uinput 才会出现）；
#   2. 写 /etc/udev/rules.d/60-quadruped-joy.rules —— 给 /dev/uinput 与"手柄类"输入设备打
#      systemd 的 uaccess 标签。uaccess 的意思是"给当前登录会话的用户一个 ACL"，所以
#      **不需要重新登录、也不需要把用户加进 input 组**（加组要重登，这里刻意避开）；
#   3. reload + trigger udev，让规则立刻生效，并给 /dev/uinput 现有节点补一次权限。
#
# 为什么需要：本机实测 /dev/uinput 是 root:root 0600、/dev/input/event* 是 root:input 0660
# 且没有 ACL —— 也就是说**真手柄插上也读不了**，仿真手柄更写不了。这条规则同时解决两个方向。
#
# 撤销：删掉 /etc/udev/rules.d/60-quadruped-joy.rules 后 `udevadm control --reload-rules` 即可。

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "需要 root：sudo $0" >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    echo "拿不到发起 sudo 的普通用户名（SUDO_USER 为空）：请用 sudo（而不是 root 登录）运行" >&2
    exit 1
fi

RULE_FILE=/etc/udev/rules.d/60-quadruped-joy.rules

echo "== 1/4 加载 uinput 模块 =="
modprobe uinput || echo "（modprobe uinput 失败，多半是已经内建，继续）"

echo "== 2/4 写 udev 规则 $RULE_FILE =="
cat > "$RULE_FILE" <<'EOF'
# 四足 ROS 2 任务（@20261005_ros2）用：给仿真手柄（/dev/uinput）与手柄读取（joystick 设备）
# 打 systemd 的 uaccess 标签 —— 当前登录会话的用户拿到 ACL，不必重新登录、不必加 input 组。
# 生成者：@20261005_ros2/scripts/setup_joy_devices.sh（删掉本文件即可撤销）。
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess"
SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_JOYSTICK}=="1", TAG+="uaccess"
EOF
cat "$RULE_FILE"

echo "== 3/4 reload 规则并补一次现有节点权限 =="
udevadm control --reload-rules
udevadm trigger --subsystem-match=misc --sysname-match=uinput
udevadm trigger --subsystem-match=input --property-match=ID_INPUT_JOYSTICK=1
# uaccess 由 logind 在 udev 事件里落 ACL；这里再显式补一次，保证"现在就能用"
if [ -e /dev/uinput ]; then
    setfacl -m "u:${TARGET_USER}:rw" /dev/uinput
fi

echo "== 4/4 结果 =="
ls -l /dev/uinput
getfacl -p /dev/uinput 2>/dev/null | grep -E "^user:" || true
echo
echo "完成。用 $TARGET_USER 的账号验证："
echo "  pixi run python @20261005_ros2/sim_joy/xbox_sim_joy.py     # 造一个仿真手柄"
echo "  pixi run ros2 run quadruped_ros2 joy_node                  # 应该报「手柄已连接」"
