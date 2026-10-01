// 命令行面：用法文本、选项表、取值结构体、几个"字符串 → 值"的解析器，以及把 argv 变成 Options 的**全部**校验。
//
// 从 main.cpp 搬出来（行为逐字不变）：main() 原先那 405 行里有一大块在回答"命令行长什么样"，
// 与"怎么跑仿真"无关，读代码的人想找控制逻辑得先翻过 200 行参数说明。
//
// 与 args.h 的分工（别把两者搞混）：
//   * args.h 管**语法**——这个选项认不认得、要不要带值、是不是多了个位置参数；
//   * 本文件管**语义**——值合不合法（枚举串认不认识、数能不能为负、范围对不对）。
// 两者都用"打印原因 + 退出 1"报错（args.h 的约定见那边的文件头）。
//
// 本文件里没有任何仿真知识：不知道模型、不知道场景、不知道状态机长什么样。
#pragma once

#include "args.h"
#include "state.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace cli {

namespace fs = std::filesystem;

inline const char *kUsage =
    "用法：motor_sim [scene.xml] [--mode view|sim|record] [--start raw|stance|rest|side]\n"
    "                 [--kp N] [--kd N] [--kd-damp N] [--ramp auto|SEC] [--gravity-comp]\n"
    "                 [--seconds N] [--script \"t:mode,...\"] [--width N] [--height N]\n"
    "                 [--out FILE] [--fps N] [--tau-max N] [--deadzone N]\n"
    "                 [--delay-cycles N] [--noise N] [--gear N]\n"
    "                 [--pitch DEG] [--roll DEG] [--floor-friction \"S [SPIN ROLL]\"] [--floor-condim N]\n"
    "\n"
    "第三次培训·子任务项一（仿真部分）：关节电机 = MIT 混合控制器（讲义 §1.2），\n"
    "控制程序是两状态的**状态机**——阻尼模式 / 站立模式，窗口里按键实时切换。\n"
    "\n"
    "  --mode view     开窗口（自己写的窗口，才有键盘切换）；默认\n"
    "  --mode sim      无窗口只仿真，跑完 --seconds 打印指标与判定（回归用）\n"
    "  --mode record   无窗口 + 录像：隐藏窗口离屏渲染 → ffmpeg；配合 --script 可做出\n"
    "                  固定脚本的演示视频（默认 output/cpp/state_machine.mp4）\n"
    "  --start …       起点：raw = 模型原姿态（默认）、stance = 搜出来的站姿、\n"
    "                  rest = 场景自带的趴卧 keyframe、side = 侧躺（绕 x 转 90° 再抬高）\n"
    "  --script …      仅 sim / record：形如 \"1:stand,5:damp,6:reset\"（到该仿真时刻切换；reset = 回起点）\n"
    "  --out FILE      仅 record：输出 MP4（相对当前目录；不给就用默认路径）\n"
    "  --fps N         仅 record：输出帧率（默认 50；出帧按仿真时间的严格网格）\n"
    "  --dump-stance FILE  把搜出来的站姿写进 FILE 后立即退出（供 cpp/essential 加载；\n"
    "                  格式与指纹见 src/stance_file.h）\n"
    "  --ramp auto|SEC  站立模式下 q_des 的斜坡：auto（默认）按按下那一刻的姿态选——\n"
    "                  还在站姿附近用 0.1 s（必须快收腿），已经趴下用 1.5 s（慢慢起）\n"
    "  --kp/--kd       站立模式的输出侧刚度/阻尼（默认 80 / 3，取讲义 §1.4 的实机配置）\n"
    "  --kd-damp       阻尼模式的阻尼（默认 0.5；这组增益决定了“软瘫”后落在什么姿势，\n"
    "                  越大腿越撑得住、越大越容易侧翻，实测见 cpp/docs/sim.md）\n"
    "  --gravity-comp  站立模式叠加 qfrc_bias 前馈（试验用；实机拿不到这个量）\n"
    "  --tau-max N     覆盖执行器限幅（默认用模型 ctrlrange ±20；实机 black 配置是 33.5）\n"
    "  --deadzone N    静摩擦死区：|τ| < N 时输出 0（默认 0 = 不建死区）\n"
    "  --delay-cycles N  指令延迟 N 个控制周期（默认 0）\n"
    "  --noise N       力矩噪声 [N·m]（默认 0；固定种子，可复现）\n"
    "  --gear N        减速比（默认 6.33）：只用于打印转子侧命令的换算，不影响仿真\n"
    "  --pitch/--roll DEG  把**平面地面**绕 y / x 轴转这么多度（默认 0 = 水平）。狗跟着转同一个\n"
    "                  旋转、**重力不动**，所以越陡越站不住；高度/倾斜/漂移都改成相对地面法向\n"
    "                  算（水平时退化成 z / 竖直度 / 水平位移，结果与不开这个功能逐位相同）。\n"
    "                  非 0 时地面自动换棋盘格纹理，否则坡度在画面上看不出来。\n"
    "  --floor-friction \"S [SPIN ROLL]\"  地面与足底的摩擦系数（默认用场景 XML 里的\n"
    "                  1 0.005 0.0001）。两边一起设：MuJoCo 的接触摩擦取两个 geom **逐元素最大**，\n"
    "                  只把地面调小不生效（足底球的 1 仍然压着）——实测见 cpp/docs/sim.md\n"
    "  --floor-condim N 接触维度（默认用场景里的 3；自旋/滚动摩擦只要 condim ≥ 4/6 才进求解）\n"
    "  --width/--height  窗口尺寸（默认 1280x720）\n"
    "\n"
    "退出码：0 = 判定通过（或 --help）、1 = 参数错误、2 = 判定不通过。\n";

inline const std::vector<OptionDef> kOptionDefs = {
    {"--mode", true},         {"--start", true},        {"--kp", true},
    {"--kd", true},           {"--kd-damp", true},      {"--ramp", true},
    {"--gravity-comp", false}, {"--seconds", true},     {"--script", true},
    {"--width", true},        {"--height", true},       {"--out", true},
    {"--fps", true},          {"--tau-max", true},      {"--dump-stance", true},
    {"--deadzone", true},     {"--delay-cycles", true}, {"--noise", true},
    {"--gear", true},         {"--pitch", true},        {"--roll", true},
    {"--floor-friction", true}, {"--floor-condim", true},
};

// 脚本动作：切状态，或者“回到起点”（= 窗口里按 R）。
// 与 ctrl::State 的区别：那是控制程序的状态，这里是**命令行脚本**的动作——多一个 reset。
enum class Action { Damping, Standing, Reset };

inline ctrl::State ToState(Action a) {
    return a == Action::Standing ? ctrl::State::Standing : ctrl::State::Damping;
}

inline const char *NameAscii(Action a) {
    return a == Action::Standing ? "stand" : (a == Action::Damping ? "damp" : "reset");
}

struct Options {
    std::string mode = "view";  // view / sim / record
    fs::path scene;             // 空 = <任务目录>/scenes/flat_scene.xml
    fs::path out;               // 仅 record：空 = <任务目录>/output/cpp/state_machine.mp4
    fs::path dump_stance;       // 非空 = 只把搜出来的站姿写进这个文件，然后退出
    double fps = 50.0;          // 仅 record
    std::string start = "raw";  // raw / stance / rest / side
    double kp = 80.0;           // 站立模式的位置刚度（关节侧）
    double kd = 3.0;            // 站立模式的阻尼
    double kd_damp = 0.5;       // 阻尼模式的阻尼（小阻尼才像真狗那样“软瘫”趴下，见 cpp/docs/sim.md）
    bool auto_ramp = true;      // --ramp auto（默认）：按按下那一刻的姿态选斜坡
    double ramp = 1.5;          // --ramp SEC 时用（也是 auto 分支里“已经趴下”那支）
    double ramp_fast = 0.1;     // auto 分支里“还在站姿附近”用的快斜坡
    bool gravity_comp = false;
    double seconds = 8.0;       // sim 模式的仿真时长
    std::vector<std::pair<double, Action>> script;
    int width = 1280, height = 720;
    double tau_max = 0.0;       // 0 = 用模型 ctrlrange
    double deadzone = 0.0;
    int delay_cycles = 0;
    double noise = 0.0;
    double gear = 6.33;         // 宇树 GO-M8010-6 的减速比（讲义 §2.1）
    double pitch = 0.0;         // --pitch DEG：地面绕 y 轴倾角（0 = 水平）
    double roll = 0.0;          // --roll DEG：地面绕 x 轴倾角
    bool friction_set = false;  // 是否显式给了 --floor-friction
    double friction[3] = {0.0, 0.0, 0.0};
    int condim = 0;             // >0 才覆盖场景里的值
};

// 解析 "1:stand,5:damp,6:reset" 这类脚本
inline bool ParseScript(const std::string &text, std::vector<std::pair<double, Action>> *out) {
    size_t pos = 0;
    while (pos <= text.size()) {
        const size_t comma = text.find(',', pos);
        const std::string item = text.substr(pos, comma == std::string::npos ? std::string::npos
                                                                            : comma - pos);
        if (!item.empty()) {
            const size_t colon = item.find(':');
            if (colon == std::string::npos) {
                std::fprintf(stderr, "--script 的每一项要写成 t:mode（如 1:stand）：%s\n", item.c_str());
                return false;
            }
            const std::string t_text = item.substr(0, colon);
            double t = 0.0;
            try {
                size_t used = 0;
                t = std::stod(t_text, &used);
                if (used != t_text.size())
                    throw std::invalid_argument("tail");
            } catch (const std::exception &) {
                std::fprintf(stderr, "--script 里的时刻不是数字：%s\n", t_text.c_str());
                return false;
            }
            const std::string what = item.substr(colon + 1);
            ctrl::State s;
            if (ctrl::ParseState(what, &s))
                out->emplace_back(t, s == ctrl::State::Standing ? Action::Standing : Action::Damping);
            else if (what == "reset")
                out->emplace_back(t, Action::Reset);
            else {
                std::fprintf(stderr, "--script 里的动作只能是 stand / damp / reset：%s\n", what.c_str());
                return false;
            }
        }
        if (comma == std::string::npos)
            break;
        pos = comma + 1;
    }
    std::stable_sort(out->begin(), out->end(),
                     [](const auto &a, const auto &b) { return a.first < b.first; });
    return true;
}

// 解析 --floor-friction："0.6" 或 "0.6 0.005 0.0001"（滑动 [自旋 滚动]，空格或逗号分隔）
inline bool ParseFriction(const std::string &text, double out[3]) {
    std::vector<double> v;
    const char *p = text.c_str();
    while (*p != '\0') {
        while (*p == ' ' || *p == '\t' || *p == ',')
            ++p;
        if (*p == '\0')
            break;
        char *end = nullptr;
        const double d = std::strtod(p, &end);
        if (end == p) {
            std::fprintf(stderr, "--floor-friction 里不是数字：%s\n", text.c_str());
            return false;
        }
        v.push_back(d);
        p = end;
    }
    if (v.size() != 1 && v.size() != 3) {
        std::fprintf(stderr, "--floor-friction 要 1 个或 3 个数（滑动 [自旋 滚动]）：%s\n",
                     text.c_str());
        return false;
    }
    out[0] = v[0];
    out[1] = v.size() == 3 ? v[1] : 0.005;
    out[2] = v.size() == 3 ? v[2] : 0.0001;
    if (out[0] < 0.0 || out[1] < 0.0 || out[2] < 0.0) {
        std::fprintf(stderr, "--floor-friction 不能为负：%s\n", text.c_str());
        return false;
    }
    return true;
}

// argv → Options（语法交给 args.h，语义全在这里）。取值不合法就打印原因 + 用法后退出 1；
// `--help/-h` 由 ParseArgs 处理（打印用法、退出 0），所以这里永远拿得到一个"干净"的 Options。
inline Options ParseOptions(int argc, char **argv) {
    const Args args = ParseArgs(argc, argv, kUsage, kOptionDefs, /*max_positional=*/1);

    Options opt;
    opt.mode = args.value("--mode", opt.mode);
    if (args.has("--mode") && opt.mode != "view" && opt.mode != "sim" && opt.mode != "record") {
        std::fprintf(stderr, "--mode 只能是 view / sim / record：%s\n%s", opt.mode.c_str(), kUsage);
        std::exit(1);
    }
    if (!args.positional.empty())
        opt.scene = args.positional[0];
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
    opt.gravity_comp = args.has("--gravity-comp");
    opt.seconds = args.number("--seconds", opt.seconds, kUsage);
    opt.width = args.integer("--width", opt.width, kUsage);
    opt.height = args.integer("--height", opt.height, kUsage);
    opt.fps = args.number("--fps", opt.fps, kUsage);
    if (args.has("--out"))
        opt.out = args.value("--out");
    if (args.has("--dump-stance"))
        opt.dump_stance = args.value("--dump-stance");
    opt.tau_max = args.number("--tau-max", opt.tau_max, kUsage);
    opt.deadzone = args.number("--deadzone", opt.deadzone, kUsage);
    opt.delay_cycles = args.integer("--delay-cycles", opt.delay_cycles, kUsage);
    opt.noise = args.number("--noise", opt.noise, kUsage);
    opt.gear = args.number("--gear", opt.gear, kUsage);
    opt.pitch = args.number("--pitch", opt.pitch, kUsage);
    opt.roll = args.number("--roll", opt.roll, kUsage);
    if (args.has("--floor-friction")) {
        opt.friction_set = true;
        if (!ParseFriction(args.value("--floor-friction"), opt.friction))
            std::exit(1);
    }
    opt.condim = args.integer("--floor-condim", opt.condim, kUsage);
    if (opt.ramp < 0.0 || opt.kp < 0.0 || opt.kd < 0.0 || opt.kd_damp < 0.0 || opt.seconds <= 0.0 ||
        opt.tau_max < 0.0 || opt.deadzone < 0.0 || opt.delay_cycles < 0 || opt.noise < 0.0 ||
        opt.gear <= 0.0 || opt.fps <= 0.0 || opt.width <= 0 || opt.height <= 0) {
        std::fprintf(stderr, "参数取值不合法（时长/增益/限幅等不能为负）：见用法\n%s", kUsage);
        std::exit(1);
    }
    if (std::fabs(opt.pitch) >= 90.0 || std::fabs(opt.roll) >= 90.0 || opt.condim < 0 ||
        opt.condim > 6) {
        std::fprintf(stderr, "--pitch/--roll 要 |角度| < 90°，--floor-condim 要在 0~6：见用法\n%s",
                     kUsage);
        std::exit(1);
    }
    if (args.has("--script") && !ParseScript(args.value("--script"), &opt.script))
        std::exit(1);
    return opt;
}

} // namespace cli
