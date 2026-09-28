// 场景装配：把"一次仿真要用到的现场"从命令行参数一路准备到可以起跑——加载场景 XML、找到地面 geom 与
// 四只脚底球、按需覆盖摩擦、搜站姿、按需摆倾斜地面、把狗摆到起点。
//
// 从 main.cpp 搬出来（行为逐字不变）：原先这 110 行和"电机怎么下指令""窗口怎么画"搅在 main() 里，
// 中间还夹着 6 处 `mj_deleteData/mj_deleteModel` 的手工清理。搬出来之后 main() 只要一句
// `setup::Prepare(opt, &scene)`，读代码的人可以先看"怎么跑"，需要时再回来看"现场怎么搭"。
//
// 顺序不是随便排的（两条硬约束，见各自处的注释）：
//   1. **站姿搜索必须在水平地面下做**——搜索里的"把基座平移到最低脚底面贴地"是水平地面的算法，
//      所以先搜、再转地面+狗（相对几何不变，搜出来的站姿照旧成立）；
//   2. **摆起点在最后**——搜索会改 qpos（见 stance.h 的 Search），所以终点状态由 start::Pose 决定。
#pragma once

#include "cli.h"
#include "ground.h"
#include "start.h"
#include "stance.h"

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <vector>

namespace setup {

namespace fs = std::filesystem;

// 装配好的一次仿真现场。**拥有** model/data（析构里释放）：这样 Prepare 中途任何一步失败
// （return false）时，已经建出来的资源都会被自动收掉，调用方不用在每条失败路径上手工清理。
// 与 viewer::Window / FrameRecorder 是同一套写法：自己持有裸句柄、析构里释放、删掉拷贝。
// 两行为什么都要写、与 = default / = 0 的区别：见 docs/learn/cpp-cmake.md 的「= delete」那条问答。
struct Scene {
    mjModel *model = nullptr;
    mjData *data = nullptr;
    fs::path root;                   // 任务目录（= 可执行文件往上两层；录像默认输出路径要用）
    int floor_geom = -1;             // 场景里名为 floor 的平面 geom（没有就是 -1）
    std::vector<int> feet;           // 4 个足底碰撞球（stance::FindFeet 查出来）
    double foot_radius = 0.0;        // 足底球半径 [m]（搜索与"落地面"都要用）
    stance::Target target;           // 站姿搜索结果 = 站立模式的控制目标
    stance::Plane plane;             // 地面（默认水平；--pitch/--roll 之后才是斜的）
    double ref[3] = {0.0, 0.0, 0.0}; // 漂移参考点 = 起点基座位置

    Scene() = default;
    ~Scene() {
        if (data != nullptr)
            mj_deleteData(data);
        if (model != nullptr)
            mj_deleteModel(model);
    }
    Scene(const Scene &) = delete;
    Scene &operator=(const Scene &) = delete;
};

// 按 opt 把现场准备好（成功返回 true；失败返回 false，原因已经打到 stderr，调用方直接返回 1）。
// 过程里的那几行 printf 是给"跑一下看看"用的摘要：换模型/换场景时最先要看的几个数都在这里。
inline bool Prepare(const cli::Options &opt, Scene *out) {
    // 固定路径：可执行文件应为 <任务目录>/cpp/build/motor_sim，往上两层就是任务目录
    const fs::path exe_dir = fs::read_symlink("/proc/self/exe").parent_path();
    const fs::path root = exe_dir.parent_path().parent_path();
    if (opt.scene.empty() && !fs::is_directory(root / "scenes")) {
        std::fprintf(stderr, "预期可执行文件在 <任务目录>/cpp/build/ 下，但 %s 里没有 scenes/\n",
                     root.c_str());
        std::fprintf(stderr, "请用第一个参数指定场景，或按 README 的构建命令重新构建。\n");
        return false;
    }
    const fs::path scene = opt.scene.empty() ? root / "scenes/flat_scene.xml" : opt.scene;
    out->root = root;

    std::printf("MuJoCo %s\n", mj_versionString());
    if (mjVERSION_HEADER != mj_version()) {
        std::fprintf(stderr, "头文件与库版本不一致，终止\n");
        return false;
    }
    std::printf("场景：%s\n", scene.c_str());

    out->model = mj_loadXML(scene.c_str(), nullptr, nullptr, 0);
    if (out->model == nullptr) {
        std::fprintf(stderr, "加载场景失败：%s\n", scene.c_str());
        return false;
    }
    mjModel *m = out->model;
    mjData *d = out->data = mj_makeData(m);
    double mass = 0.0;
    for (int b = 1; b < m->nbody; ++b)
        mass += m->body_mass[b];
    std::printf("模型：nq=%ld nv=%ld nu=%ld dt=%g s；总质量 %.3f kg；执行器 ctrlrange ±%.0f N·m\n",
                static_cast<long>(m->nq), static_cast<long>(m->nv), static_cast<long>(m->nu),
                m->opt.timestep, mass, m->actuator_ctrlrange[1]);

    // 地面：平面 geom（场景里的 floor）。摩擦/接触维度可覆盖，倾角可调（默认都不动）
    const int floor_geom = out->floor_geom = mj_name2id(m, mjOBJ_GEOM, "floor");

    // 脚（4 个足底碰撞球）+ 站姿搜索
    out->feet = stance::FindFeet(m, &out->foot_radius);
    const std::vector<int> &feet = out->feet;
    std::printf("脚：%zu 个足底碰撞球（半径 %.3f m）\n", feet.size(), out->foot_radius);
    if (feet.size() != 4) {
        std::fprintf(stderr, "没找到 4 个足底球，模型不对？\n");
        return false;
    }
    // 摩擦/接触维度：给了才改（不给就用场景 XML 里的值，结果与加这个开关之前逐位相同）
    if (opt.friction_set || opt.condim > 0) {
        ground::SetFriction(m, floor_geom, feet, opt.friction_set ? opt.friction : nullptr,
                            opt.condim);
        const char *src = opt.friction_set ? "--floor-friction" : "场景 XML";
        std::printf("摩擦（%s）：地面/足底 %.4g %.4g %.4g、condim %d", src,
                    floor_geom >= 0 ? m->geom_friction[3 * floor_geom] : 0.0,
                    floor_geom >= 0 ? m->geom_friction[3 * floor_geom + 1] : 0.0,
                    floor_geom >= 0 ? m->geom_friction[3 * floor_geom + 2] : 0.0,
                    floor_geom >= 0 ? m->geom_condim[floor_geom] : 0);
        if (opt.condim == 3 || (opt.condim == 0 && floor_geom >= 0 && m->geom_condim[floor_geom] == 3))
            std::printf("（condim=3 只用滑动摩擦，后面两个数不参与求解）");
        std::printf("\n");
    }
    // 注意：搜索**必须在水平地面下做**（见文件头第 1 条），所以这一段在 ApplyTilt 之前
    out->target = stance::Search(m, d, feet, out->foot_radius);
    if (!out->target.ok) {
        std::fprintf(stderr, "站姿搜索失败\n");
        return false;
    }
    const stance::Target &target = out->target;
    std::printf("站姿（搜索得到，不读 keyframe）：膝 %.2f rad、大腿 %.2f×膝；基座 z=%.4f m、"
                "质心离四足中心 %.4f m、四足触地 %d\n",
                target.bend, target.frac, target.z, target.com_err, target.feet);

    // 地面倾角：站姿搜索必须在**水平**地面下做（搜索里的"基座平移到最低脚底面贴地"是水平地面
    // 的算法），所以先搜、再转地面+狗（相对几何不变，搜出来的站姿照旧成立）。
    {
        char err[256] = "";
        if (!ground::ApplyTilt(m, d, floor_geom, opt.pitch, opt.roll, &out->plane, err,
                               sizeof(err))) {
            std::fprintf(stderr, "%s\n", err);
            return false;
        }
        if (out->plane.level()) {
            std::printf("地面：水平（--pitch/--roll 都是 0），重力不动\n");
        } else {
            // 地面转了之后，"又平、又无限、又没纹理"的地面从重力水平的相机看过去看不出坡度，
            // 把场景里备好的棋盘格材质挂上去（材质默认不用，见 scenes/flat_scene.xml）
            const int mat = mj_name2id(m, mjOBJ_MATERIAL, "floor_grid_mat");
            if (floor_geom >= 0 && mat >= 0)
                m->geom_matid[floor_geom] = mat;
            const double *xmat = d->geom_xmat + 9 * floor_geom;
            std::printf("地面：倾角 %.2f°（pitch %.1f° / roll %.1f°），法向 (%.3f, %.3f, %.3f)；"
                        "地面 geom 实测法向 (%.3f, %.3f, %.3f)；**重力不动**（越陡越站不住）；"
                        "棋盘格纹理已挂上\n",
                        std::acos(std::clamp(out->plane.up[2], -1.0, 1.0)) * 180.0 / M_PI, opt.pitch,
                        opt.roll, out->plane.up[0], out->plane.up[1], out->plane.up[2], xmat[2],
                        xmat[5], xmat[8]);
        }
    }

    if (!start::Pose(m, d, opt.start, target, feet, out->foot_radius, out->plane))
        return false;
    out->ref[0] = d->qpos[0]; // 漂移参考点 = 起点基座位置
    out->ref[1] = d->qpos[1];
    out->ref[2] = d->qpos[2];
    return true;
}

} // namespace setup
