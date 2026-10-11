#!/usr/bin/env python3
"""实验 1：列出本版 rclpy 有哪些名称校验器，并逐项试。

跑法（仓库根）：pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/val.py
结论见 docs/learn/ros2-graph-and-clock.md §3。"""
import inspect
import rclpy
from rclpy.exceptions import (
    InvalidNamespaceException, InvalidNodeNameException,
    InvalidParameterException, InvalidServiceNameException,
    InvalidTopicNameException,
)
from rclpy.validate_namespace import validate_namespace
from rclpy.validate_node_name import validate_node_name
from rclpy.validate_topic_name import validate_topic_name
from rclpy.validate_full_topic_name import validate_full_topic_name
from rclpy.validate_parameter_name import validate_parameter_name
from rclpy.expand_topic_name import expand_topic_name

print("### INVENTORY: rclpy.validate_* that exist in this version")
mods = [
    ("rclpy.validate_node_name.validate_node_name", validate_node_name),
    ("rclpy.validate_namespace.validate_namespace", validate_namespace),
    ("rclpy.validate_topic_name.validate_topic_name", validate_topic_name),
    ("rclpy.validate_full_topic_name.validate_full_topic_name", validate_full_topic_name),
    ("rclpy.validate_parameter_name.validate_parameter_name", validate_parameter_name),
    ("rclpy.expand_topic_name.expand_topic_name", expand_topic_name),
]
for name, fn in mods:
    print(f"  {name}{inspect.signature(fn)}")
print("  rclpy.validate_service_name: DOES NOT EXIST (use validate_topic_name(n, is_service=True))")
print(f"  rclpy.validate module: DOES NOT EXIST (ModuleNotFoundError)")

CASES = [
    "", "foo", "/foo", "//foo", "/foo/", "foo/bar", "1foo", "foo-1", "foo bar",
    "~foo", "~", "{}", "a" * 256, "a" * 255, "naïve", "机器人", "_foo", "foo_",
    "foo.bar", "foo..bar", "foo/../bar", "/", "foo/", "foo//bar",
]

def show(label, fn):
    print(f"\n### {label}")
    for s in CASES:
        disp = s if len(s) <= 20 else f"{s[:12]}...({len(s)} chars)"
        if s == "":
            disp = "<empty>"
        try:
            fn(s)
            print(f"  {disp:>22} | VALID   | -")
        except Exception as e:
            msg = str(e).replace("\n", " ")
            print(f"  {disp:>22} | INVALID | {type(e).__name__}: {msg}")

show("validate_node_name(x)", validate_node_name)
show("validate_namespace(x)", validate_namespace)
show("validate_topic_name(x)", validate_topic_name)
show("validate_topic_name(x, is_service=True)  [service names]",
     lambda s: validate_topic_name(s, is_service=True))
show("validate_full_topic_name(x)", validate_full_topic_name)
show("validate_parameter_name(x)", validate_parameter_name)

print("\n### expand_topic_name(name, node_name, namespace)  -> fully-qualified name")
for nm in ["rel_topic", "/abs_topic", "~/priv_topic", "sub/child", "~", "/", "//x"]:
    try:
        print(f"  {nm!r:>14} + node='probe' ns='/robot1' -> {expand_topic_name(nm, 'probe', '/robot1')!r}")
    except Exception as e:
        print(f"  {nm!r:>14} + node='probe' ns='/robot1' -> {type(e).__name__}: {str(e).splitlines()[0]}")

print("\n### expand_topic_name with node name containing '/' (private-name resolution)")
for nd in ["probe", "a/b", "probe2"]:
    try:
        print(f"  node={nd!r:>8} ns=/robot1 '~/p' -> {expand_topic_name('~/p', nd, '/robot1')!r}")
    except Exception as e:
        print(f"  node={nd!r:>8} ns=/robot1 '~/p' -> {type(e).__name__}: {str(e).splitlines()[0]}")
