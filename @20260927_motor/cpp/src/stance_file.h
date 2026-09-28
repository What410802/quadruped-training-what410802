// 站姿文件的**格式**与**指纹**：把"搜出来的站姿"存成一个小文本文件，下次直接加载，不必再搜。
//
// 为什么值得存：站姿只由**模型**决定（关节限位、几何、质量），跟场景/控制参数都无关，
// 所以同一份模型搜出来的结果每次都一样——那就没必要每次启动都再算一遍（也省得让"最简版"
// 背着整套搜索代码）。文件放在 `<任务目录>/models/stance.txt`（模型旁边）。
//
// 两半的归属（本仓库有完整版与最简版两份代码，站姿文件的读写各占一半）：
//   * 完整版 [`../src/stance.h`](../src/stance.h) 有 `stance::Search`，于是由它来**写**：
//     `motor_sim --dump-stance <文件>`；
//   * 最简版没有搜索，于是只**读**（见 `../essential/src/stance_file.h`）。
//   下面两个 Fingerprint 函数就是"格式"的定义：两边必须一起改，改完记得让文件重新生成。
//
// 格式（# 开头是注释，键值行都是 `键 值...`；q 是**执行器顺序**的关节角，与 stance.h 一致）：
//
//     version 1
//     model nq=19 nv=18 nu=12 nbody=20 ngeom=95 mass=13.247200
//     feet count=4 radius=0.020000
//     search bend=1.100000 frac=0.550000 com_err=0.000900 feet=4
//     z 0.49729999999999996
//     q 0 0 0 0 0 0 0 0 0 0 0 0
//
//   * `model` 与 `feet` 两行是**指纹**：加载时逐字比对，不一致就拒绝加载（宁可报错，
//     也不要偷偷用一个不属于当前模型的站姿）；
//   * `search` 行只作记录（谁搜出来的、质心偏差多少），不参与校验；
//   * 数字用 %.17g 写，保证读回来与搜出来的 double **逐位相同**（这样物理结果能直接对拍）。
#pragma once

#include "stance.h"

#include <mujoco/mujoco.h>

#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

namespace stance {

namespace fs = std::filesystem;

// 文件格式版本：格式一改就得 +1（加载端认不得就报错，而不是猜）
inline constexpr int kFileVersion = 1;

// 模型指纹：够"认出是同一个模型"就行（自由度、实体/几何数、总质量）。总质量与 scene_setup 里
// 打印的那个一样，都是 body 1.. 的和——用同一个式子算，免得两处对不上。
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

// 脚指纹：足底球个数与半径（站姿的基座高度就是靠"最低那只脚底球刚好贴地"算的，半径错了全错）
inline std::string FeetFingerprint(size_t count, double radius) {
    char buf[128];
    std::snprintf(buf, sizeof(buf), "feet count=%zu radius=%.6f", count, radius);
    return buf;
}

// 把站姿写成文件（供最简版加载）。写成功返回 true；打不开/写不进返回 false（调用方报错）。
inline bool SaveToFile(const fs::path &path, const mjModel *m, const std::vector<int> &feet,
                       double foot_radius, const Target &target) {
    if (path.has_parent_path()) { // 目录不存在就顺手建出来（与 recorder 的写法一致）
        std::error_code ec;
        fs::create_directories(path.parent_path(), ec);
    }
    std::FILE *f = std::fopen(path.string().c_str(), "w");
    if (f == nullptr)
        return false;

    std::fprintf(f,
                 "# 站姿（stance）：站立模式的控制目标 q_des 与该姿态下的基座高度。\n"
                 "#\n"
                 "# 它是**搜索结果**：由 cpp/src 版（含 stance::Search）生成一次，cpp/essential 版直接加载。\n"
                 "# 生成/更新（换了模型、或改了搜索参数就重跑这一条）：\n"
                 "#   pixi run @20260927_motor/cpp/build/motor_sim --dump-stance @20260927_motor/models/stance.txt\n"
                 "# 加载时会逐字比对 model / feet 两行指纹，不一致就拒绝加载。\n"
                 "# 格式说明见 cpp/src/stance_file.h。\n");
    std::fprintf(f, "version %d\n", kFileVersion);
    std::fprintf(f, "%s\n", ModelFingerprint(m).c_str());
    std::fprintf(f, "%s\n", FeetFingerprint(feet.size(), foot_radius).c_str());
    std::fprintf(f, "search bend=%.6f frac=%.6f com_err=%.6f feet=%d\n", target.bend, target.frac,
                 target.com_err, target.feet);
    std::fprintf(f, "z %.17g\n", target.z);
    std::fprintf(f, "q");
    for (double v : target.q)
        std::fprintf(f, " %.17g", v);
    std::fprintf(f, "\n");
    return std::fclose(f) == 0;
}

} // namespace stance
