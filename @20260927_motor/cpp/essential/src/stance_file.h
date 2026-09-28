// 站姿文件的**加载**这一半（格式与指纹的定义在 [`../../src/stance_file.h`](../../src/stance_file.h)：
// 两边的 `ModelFingerprint` / `FeetFingerprint` 必须一致，改格式要同时改两份）。
//
// 最简版没有 `stance::Search`：站姿是**预先算好**存起来的（默认 `<任务目录>/models/stance.txt`），
// 启动时只做三件事——打开、对指纹、把 q/z 装进 `stance::Target`。这样启动不必再跑一遍搜索，
// 也不必让"最简版"背着整套搜索代码。指纹不符就报错退出（宁可报错，也不要偷偷用一个不属于
// 当前模型的站姿），调用方在报错里给出重新生成的命令。
//
// 格式（完整说明在 [`../../src/stance_file.h`](../../src/stance_file.h)；`#` 开头是注释，键值行是
// `键 值…`，q 是**执行器顺序**的关节角，与 stance.h 一致）：
//
//     version 1
//     model nq=19 nv=18 nu=12 nbody=20 ngeom=50 mass=13.247180
//     feet count=4 radius=0.020000
//     search bend=1.700000 frac=0.550000 com_err=0.010126 feet=4
//     z 0.4000802544414247
//     q 0 0.94600000000000006 -1.6890000000000001 0 -0.94600000000000006 1.6890000000000001 0 -0.94600000000000006 1.6890000000000001 0 0.94600000000000006 -1.6890000000000001
//
//   * `model` / `feet` 是**指纹**：与当前模型逐字比对，不符就报错；
//   * 最简版只读 `version` / `model` / `feet` / `z` / `q` 这五行，`search` 行**不读**（它是生成
//     者的记录：用什么弯曲量搜出来的、质心偏差多少，写在文件里是给对拍和复现用的）；
//   * 不认得的键直接忽略（格式只增不改，这样以后加字段不用同步升版本号）。
#pragma once

#include "stance.h"

#include <mujoco/mujoco.h>

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace stance {

namespace fs = std::filesystem;

// 文件格式版本：与 ../src/stance_file.h 的那个数字必须相同
inline constexpr int kFileVersion = 1;

// 模型指纹：够"认出是同一个模型"就行（自由度、实体/几何数、总质量）。
// 总质量与 scene_setup 打印的那个一样，都是 body 1.. 的和——用同一个式子算，免得两处对不上。
inline std::string ModelFingerprint(const mjModel *m) {
    double mass = 0.0;
    for (int b = 1; b < m->nbody; ++b)
        mass += m->body_mass[b];
    char buf[256];
    std::snprintf(buf, sizeof(buf), "model nq=%ld nv=%ld nu=%ld nbody=%ld ngeom=%ld mass=%.6f",
                  static_cast<long>(m->nq), static_cast<long>(m->nv), static_cast<long>(m->nu),
                  static_cast<long>(m->nbody), static_cast<long>(m->ngeom), mass);
    return buf;
}

// 脚指纹：足底球个数与半径（站姿的基座高度就是靠"最低那只脚底球刚好贴地"定的，半径错了全错）
inline std::string FeetFingerprint(size_t count, double radius) {
    char buf[128];
    std::snprintf(buf, sizeof(buf), "feet count=%zu radius=%.6f", count, radius);
    return buf;
}

// ---------- 下面是这几个小工具，只给 LoadFromFile 用 ----------

inline std::string Trim(const std::string &s) {
    const size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos)
        return "";
    const size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

// 一行里的所有数字（给 `q` 用）
inline std::vector<double> ParseNumbers(const std::string &s) {
    std::vector<double> out;
    std::istringstream in(s);
    double v = 0.0;
    while (in >> v)
        out.push_back(v);
    return out;
}

// 从文件加载站姿：成功返回 true（`out->ok` 同时置上）；失败返回 false，原因写进 err。
inline bool LoadFromFile(const fs::path &path, const mjModel *m, const std::vector<int> &feet,
                         double foot_radius, Target *out, std::string *err) {
    std::ifstream in(path);
    if (!in)
        return *err = "打不开（文件不存在？没有读权限？）", false;

    std::string line, model_in, feet_in;
    int version = -1;
    bool have_z = false;
    double z = 0.0;
    std::vector<double> q;
    bool have_q = false;
    while (std::getline(in, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == '#')
            continue;
        const size_t sp = line.find(' ');
        const std::string key = line.substr(0, sp);      // 键
        const std::string rest = sp == std::string::npos ? std::string() : Trim(line.substr(sp + 1));
        if (key == "version") {
            version = std::atoi(rest.c_str());
        } else if (key == "model") {
            model_in = line;                             // 整行留着逐字比对
        } else if (key == "feet") {
            feet_in = line;
        } else if (key == "z") {
            z = std::strtod(rest.c_str(), nullptr);
            have_z = true;
        } else if (key == "q") {
            q = ParseNumbers(rest);
            have_q = true;
        }
        // 其它键：不认就忽略（见文件头）
    }

    if (version < 0)
        return *err = "没有 version 行", false;
    if (version != kFileVersion)
        return *err = "格式版本不符：文件是 " + std::to_string(version) + "，本程序认 " +
                      std::to_string(kFileVersion) + "（格式改过？重新生成一份）",
               false;
    const std::string want_model = ModelFingerprint(m);
    if (model_in != want_model)
        return *err = "模型指纹不符：\n    文件：" + model_in + "\n    当前：" + want_model, false;
    const std::string want_feet = FeetFingerprint(feet.size(), foot_radius);
    if (feet_in != want_feet)
        return *err = "脚指纹不符：\n    文件：" + feet_in + "\n    当前：" + want_feet, false;
    if (!have_z)
        return *err = "没有 z 行", false;
    if (!have_q)
        return *err = "没有 q 行", false;
    if (q.size() != static_cast<size_t>(m->nu))
        return *err = "q 有 " + std::to_string(q.size()) + " 个数，模型有 " +
                      std::to_string(m->nu) + " 个执行器",
               false;

    out->q = q;
    out->z = z;
    out->ok = true;
    return true;
}

} // namespace stance
