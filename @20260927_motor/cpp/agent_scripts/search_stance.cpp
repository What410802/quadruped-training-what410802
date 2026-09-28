// 站姿搜索（一次性工具，不进 CMake）：在完整版 `../src/stance.h` 的搜索口径上多一个
// "整条腿绕髋旋转"的自由度，用来重新搜站姿。`../essential_core` 内联的那份就是这么来的。
//
// 与完整版一致的地方：髋保持模型默认位形；左右腿的膝符号由限位区间决定；基座平移到
// "最低那只脚底面刚好贴地"；再按 1 mm 步长往下压，直到真的数出 4 个足底接触。
// 多出来的地方：`lean`（整条腿绕髋旋转）——"理想站姿的质心在四足中心上"在**稳态**下并不成立
// （PD 下沉会把质心带到脚中心后面约 1.2 cm），所以要让稳态四脚受力均匀，得先在理想站姿里往前偏一点。
// 实测数据与结论见 `../essential/README.md` 的「站姿为什么可以预存」与「验证」两节。
//
// 编译与运行（本工具不进 CMake，按需编译；MuJoCo 由 pixi 环境提供）：
//   cd <仓库根目录>
//   pixi run bash -c 'g++ -O2 -std=c++17 -I$CONDA_PREFIX/include -o /tmp/search_stance \
//       @20260927_motor/cpp/agent_scripts/search_stance.cpp \
//       -L$CONDA_PREFIX/lib -Wl,-rpath,$CONDA_PREFIX/lib -lmujoco -lpthread'
//   /tmp/search_stance @20260927_motor/scenes/flat_scene.xml 1.7 0.55 -0.011 /tmp/st.txt
//
// 位置参数：search_stance <场景.xml> <bend> <frac> <lean> <输出文件>
//   bend : 膝弯曲量 [rad]（完整版扫 0.9/1.1/1.3；essential_core 那份是 1.7）
//   frac : 大腿 = frac × 膝（完整版扫 0.1..1.0，选中 0.55）
//   lean : 整条腿绕髋旋转 [rad]（哪边是"质心前移"实测即知；−0.011 对应前移约 1.0 cm）
//   输出：与 `../models/stance.txt` 同格式的站姿文件（指纹逐字一致，可直接被
//         `../essential/src/stance_file.h` 或抽检脚本加载）
//
// 当前 essential_core 内联的那份站姿就是这个命令生成的（z / q 与 `state.h` 的
// `kStanceZ` / `kStanceQ` 逐位相同）：
//   search_stance scenes/flat_scene.xml 1.7 0.55 -0.011 out.txt
#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

int main(int argc, char **argv) {
    if (argc < 6) {
        std::fprintf(stderr, "用法：search_stance <scene.xml> <bend> <frac> <lean> <out.txt>\n");
        return 1;
    }
    const double bend = std::atof(argv[2]);
    const double frac = std::atof(argv[3]);
    const double lean = std::atof(argv[4]);
    const std::string out_path = argv[5];

    char err[512];
    mjModel *m = mj_loadXML(argv[1], nullptr, err, sizeof(err));
    if (m == nullptr) {
        std::fprintf(stderr, "%s\n", err);
        return 1;
    }
    mjData *d = mj_makeData(m);
    mj_forward(m, d);

    // 足底球（与 stance::FindFeet 同口径）+ 半径
    std::vector<int> feet;
    double foot_radius = 0.0;
    for (int g = 0; g < m->ngeom; ++g) {
        if (m->geom_type[g] == mjGEOM_SPHERE && m->geom_contype[g] != 0) {
            feet.push_back(g);
            foot_radius = m->geom_size[3 * g];
        }
    }
    if (feet.size() != 4) {
        std::fprintf(stderr, "足底球不是 4 个（%zu）\n", feet.size());
        return 1;
    }
    // 四足触地数（只看"机器人 ↔ 地面"的接触，且只认脚底球）
    const auto feet_on_ground = [&]() {
        std::vector<int> hit;
        for (int c = 0; c < d->ncon; ++c) {
            const int g1 = d->contact[c].geom[0], g2 = d->contact[c].geom[1];
            const bool f1 = m->geom_bodyid[g1] == 0, f2 = m->geom_bodyid[g2] == 0;
            if (f1 == f2)
                continue;
            const int other = f1 ? g2 : g1;
            if (std::find(feet.begin(), feet.end(), other) == feet.end())
                continue;
            if (std::find(hit.begin(), hit.end(), other) == hit.end())
                hit.push_back(other);
        }
        return static_cast<int>(hit.size());
    };

    // 左右腿膝的符号：由限位区间决定（与完整版同一条规则）
    const int nleg = m->nu / 3;
    std::vector<double> calf_sign(static_cast<size_t>(nleg), 1.0);
    for (int leg = 0; leg < nleg; ++leg) {
        const int j = m->actuator_trnid[2 * (3 * leg + 2)];
        calf_sign[static_cast<size_t>(leg)] = (m->jnt_range[2 * j + 1] < 0.0) ? -1.0 : 1.0;
    }

    // 摆站姿：髀 = 默认位形；膝 = sign·bend；大腿 = −sign·bend·frac；**整条腿再绕髀倾 lean**
    // （大腿、膝同时加 sign·lean，膝的相对角不变 ⇒ 整条腿刚体旋转）
    for (int leg = 0; leg < nleg; ++leg) {
        const double s = calf_sign[static_cast<size_t>(leg)];
        for (int k = 0; k < 3; ++k) {
            const int i = 3 * leg + k;
            const int j = m->actuator_trnid[2 * i];
            const int adr = m->jnt_qposadr[j];
            double v = m->qpos0[adr];
            if (k == 2)
                v = s * bend + s * lean;
            if (k == 1)
                v = -s * bend * frac + s * lean;
            if (m->jnt_limited[j])
                v = std::clamp(v, m->jnt_range[2 * j], m->jnt_range[2 * j + 1]);
            d->qpos[adr] = v;
        }
    }

    // 基座平移到"最低那只脚底面刚好贴地"（先按球心算，再 1 mm 步长压到真出现 4 个接触）
    const double z0 = d->qpos[2];
    mj_forward(m, d);
    double minz = 1e9;
    for (int g : feet)
        minz = std::min(minz, static_cast<double>(d->geom_xpos[3 * g + 2]));
    d->qpos[2] = z0 - (minz - foot_radius);
    mj_forward(m, d);
    int pressed = 0;
    while (feet_on_ground() < 4 && pressed < 20) {
        d->qpos[2] -= 0.001;
        mj_forward(m, d);
        ++pressed;
    }

    // 量测：基座高度、质心、四足中心、各脚高度/位置
    double fx = 0.0, fy = 0.0, zmin = 1e9, zmax = -1e9;
    for (int g : feet) {
        fx += d->geom_xpos[3 * g];
        fy += d->geom_xpos[3 * g + 1];
        zmin = std::min(zmin, static_cast<double>(d->geom_xpos[3 * g + 2]));
        zmax = std::max(zmax, static_cast<double>(d->geom_xpos[3 * g + 2]));
    }
    fx /= static_cast<double>(feet.size());
    fy /= static_cast<double>(feet.size());
    const double com_x = d->subtree_com[3];
    const double com_y = d->subtree_com[4];
    const double com_err = std::hypot(com_x - fx, com_y - fy);
    double x_rear = 1e9, x_front = -1e9;
    for (int g : feet) {
        x_rear = std::min(x_rear, static_cast<double>(d->geom_xpos[3 * g]));
        x_front = std::max(x_front, static_cast<double>(d->geom_xpos[3 * g]));
    }

    std::printf("bend=%.3f frac=%.3f lean=%+.3f | z=%.6f 质心x=%+.4f 四足中心x=%+.4f "
                "偏移=%+.4f | 后缘 %+.3f 前缘 %+.3f (余量 后 %.3f / 前 %.3f) | 触地 %d 脚高差 %.4f\n",
                bend, frac, lean, d->qpos[2], com_x, fx, com_x - fx, x_rear, x_front,
                com_x - x_rear, x_front - com_x, feet_on_ground(), zmax - zmin);

    // 写出站姿文件（格式 = models/stance.txt，指纹与 stance_file.h 的算法逐字一致）
    double mass = 0.0;
    for (int b = 1; b < m->nbody; ++b)
        mass += m->body_mass[b];
    FILE *f = std::fopen(out_path.c_str(), "w");
    if (f == nullptr) {
        std::fprintf(stderr, "写不开：%s\n", out_path.c_str());
        return 1;
    }
    std::fprintf(f, "# 站姿：由 agent_scripts/search_stance.cpp 生成（bend=%.6f frac=%.6f lean=%.6f）\n",
                 bend, frac, lean);
    std::fprintf(f, "version 1\n");
    std::fprintf(f, "model nq=%ld nv=%ld nu=%ld nbody=%ld ngeom=%ld mass=%.6f\n",
                 static_cast<long>(m->nq), static_cast<long>(m->nv), static_cast<long>(m->nu),
                 static_cast<long>(m->nbody), static_cast<long>(m->ngeom), mass);
    std::fprintf(f, "feet count=%zu radius=%.6f\n", feet.size(), foot_radius);
    std::fprintf(f, "search bend=%.6f frac=%.6f com_err=%.6f feet=%d\n", bend, frac, com_err,
                 feet_on_ground());
    std::fprintf(f, "z %.17g\n", d->qpos[2]);
    std::fprintf(f, "q");
    for (int i = 0; i < m->nu; ++i)
        std::fprintf(f, " %.17g", d->qpos[m->jnt_qposadr[m->actuator_trnid[2 * i]]]);
    std::fprintf(f, "\n");
    std::fclose(f);
    std::printf("     -> %s\n", out_path.c_str());

    mj_deleteData(d);
    mj_deleteModel(m);
    return 0;
}
