// 命令行面：用法文本、选项表、取值结构体，以及把 argv 变成 Options 的**全部**校验。
//
// 从 [`../../src/cli.h`](../../src/cli.h) 精简而来：没有 `--mode/--script/--out/--fps/--seconds`
// （只留窗口这一种模式）、没有倾斜地面与摩擦（`--pitch/--roll/--floor-*`）、没有电机非理想项
// （`--tau-max/--deadzone/--delay-cycles/--noise`）与 `--gravity-comp/--gear`；相应地也就不用管
// 脚本动作（`Action`）与摩擦字符串这两个解析器，窗口尺寸也不用给（官方界面自己管窗口）。
//
// 与 args.h 的分工（别把两者搞混）：
//   * args.h 管**语法**——这个选项认不认得、要不要带值、是不是多了个位置参数；
//   * 本文件管**语义**——值合不合法（枚举串认不认识、数能不能为负、范围对不对）。
#pragma once

#include "args.h"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

namespace cli {

namespace fs = std::filesystem;

inline const char *kUsage =
    "用法：essential_sim [scene.xml] [--start raw|stance|rest|side]\n"
    "                    [--kp N] [--kd N] [--kd-damp N] [--ramp auto|SEC] [--stance FILE]\n"
    "\n"
    "第三次培训·第一部分（仿真）的最简版：关节电机 = MIT 混合控制器（讲义 §1.2），\n"
    "控制程序是两状态的**状态机**——阻尼模式 / 站立模式。\n"
    "\n"
    "窗口是 MuJoCo **官方**的 Simulate 界面（相机、暂停/调速、关节表都在里面），按键在**这个终端**里按：\n"
    "\n"
    "  S = 站立模式    D = 阻尼模式    R = 回到起点    Q / Ctrl-C = 退出\n"
    "  （窗口里空格 = 暂停/继续，暂停时仿真不推进；直接关窗也能退出。）\n"
    "\n"
    "  --start …       起点：raw = 模型原姿态（默认）、stance = 站姿文件里的那个站姿、\n"
    "                  rest = 场景自带的趴卧 keyframe、side = 侧躺（绕 x 转 90° 再抬高）\n"
    "  --kp/--kd       站立模式的输出侧刚度/阻尼（默认 80 / 3，取讲义 §1.4 的实机配置）\n"
    "  --kd-damp       阻尼模式的阻尼（默认 0.5；这组增益决定了“软瘫”后落在什么姿势）\n"
    "  --stance FILE   站姿文件（默认 <任务目录>/models/stance.txt）——站姿由 cpp/src 版预先搜好\n"
    "                  写进这个文件，本程序只加载不搜索；与当前模型不符会直接报错\n"
    "  --ramp auto|SEC  站立模式下 q_des 的斜坡：auto（默认）按按下那一刻的姿态选——\n"
    "                  还在站姿附近用 0.1 s（必须快收腿），已经趴下用 1.5 s（慢慢起）\n"
    "\n"
    "退出码：0 = 正常退出（含 --help）、1 = 参数错误。\n"
    "（要跑无窗口回归、录像、倾斜地面/摩擦、电机非理想项，用 cpp/src/ 那个版本。）\n";

inline const std::vector<OptionDef> kOptionDefs = {
    {"--start", true},  {"--kp", true},     {"--kd", true},
    {"--kd-damp", true}, {"--ramp", true},   {"--stance", true},
};

struct Options {
    fs::path scene;             // 空 = 往上找到带 scenes/ 的目录下的 scenes/flat_scene.xml
    fs::path stance_file;       // 空 = 同一个任务目录下的 models/stance.txt
    std::string start = "raw";  // raw / stance / rest / side
    double kp = 80.0;           // 站立模式的位置刚度（关节侧）
    double kd = 3.0;            // 站立模式的阻尼
    double kd_damp = 0.5;       // 阻尼模式的阻尼（小阻尼才像真狗那样“软瘫”趴下）
    bool auto_ramp = true;      // --ramp auto（默认）：按按下那一刻的姿态选斜坡
    double ramp = 1.5;          // --ramp SEC 时用（也是 auto 分支里“已经趴下”那支）
    double ramp_fast = 0.1;     // auto 分支里“还在站姿附近”用的快斜坡
};

// argv → Options（语法交给 args.h，语义全在这里）。取值不合法就打印原因 + 用法后退出 1；
// `--help/-h` 由 ParseArgs 处理（打印用法、退出 0），所以这里永远拿得到一个"干净"的 Options。
inline Options ParseOptions(int argc, char **argv) {
    const Args args = ParseArgs(argc, argv, kUsage, kOptionDefs, /*max_positional=*/1);

    Options opt;
    if (!args.positional.empty())
        opt.scene = args.positional[0];
    if (args.has("--stance"))
        opt.stance_file = args.value("--stance");
    opt.start = args.value("--start", opt.start);
    if (opt.start != "raw" && opt.start != "stance" && opt.start != "rest" && opt.start != "side") {
        std::fprintf(stderr, "--start 只能是 raw / stance / rest / side：%s\n%s", opt.start.c_str(),
                     kUsage);
        std::exit(1);
    }
    opt.kp = args.number("--kp", opt.kp, kUsage);
    opt.kd = args.number("--kd", opt.kd, kUsage);
    opt.kd_damp = args.number("--kd-damp", opt.kd_damp, kUsage);
    if (args.has("--ramp")) { // auto = 默认：按按下那一刻的姿态选（见 state.h）
        const std::string v = args.value("--ramp");
        if (v == "auto") {
            opt.auto_ramp = true;
        } else {
            opt.auto_ramp = false;
            opt.ramp = Args::ParseNum(v, "--ramp", kUsage);
        }
    }
    if (opt.ramp < 0.0 || opt.kp < 0.0 || opt.kd < 0.0 || opt.kd_damp < 0.0) {
        std::fprintf(stderr, "参数取值不合法（斜坡/增益不能为负）：见用法\n%s", kUsage);
        std::exit(1);
    }
    return opt;
}

} // namespace cli
