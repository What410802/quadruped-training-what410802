// 场景装配：把"一次仿真要用到的现场"从命令行参数一路准备到可以起跑——加载场景 XML、
// 找到四只脚底球、**读站姿文件**（不搜索）、把狗摆到起点。
//
// 从 main.cpp 搬出来（行为逐字不变）。为什么它是一个独立的头文件：main() 应该只回答"怎么跑"，
// "现场怎么搭"是另一件事；搬出来之后 main() 只要一句 `setup::Prepare(opt, &scene)`。
//
// 本文件是 [`../../src/scene_setup.h`](../../src/scene_setup.h) 的最简版，两点不同：
//   * 去掉了摩擦/接触维度的覆盖与倾斜地面（那两件事都在 src 的 ground.h 里），
//     所以也不再需要 floor geom 与 ground.h；
//   * 站姿不搜索：从 `--stance`（默认 `<任务目录>/models/stance.txt`）加载，见 stance_file.h。
//     那个文件是完整版搜出来写的；站姿只由模型决定，指纹不符就报错，不会将就。
#pragma once

#include "cli.h"
#include "stance_file.h"
#include "start.h"
#include "stance.h"

#include <mujoco/mujoco.h>

#include <cstdio>
#include <filesystem>
#include <vector>

namespace setup {

namespace fs = std::filesystem;

// 装配好的一次仿真现场。**拥有** model/data（析构里释放）：这样 Prepare 中途任何一步失败
// （return false）时，已经建出来的资源都会被自动收掉，调用方不用在每条失败路径上手工清理。
// 与 [`../../src/viewer.h`](../../src/viewer.h) 的 Window 是同一套写法：自己持有裸句柄、析构里释放、删掉拷贝。
// 两行为什么都要写、与 = default / = 0 的区别：见 docs/learn/cpp-cmake.md 的「= delete」那条问答。
struct Scene {
    mjModel *model = nullptr;
    mjData *data = nullptr;
    fs::path scene_path;             // 实际加载的那个 XML（官方界面的 Load 要一个名字）
    std::vector<int> feet;           // 4 个足底碰撞球（stance::FindFeet 查出来）
    double foot_radius = 0.0;        // 足底球半径 [m]（搜索要用）
    stance::Target target;           // 站姿搜索结果 = 站立模式的控制目标
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

    // 把 m/d 的**所有权**交出去：官方界面 Load() 之后 m/d 归它释放（它的析构里会 mj_delete*），
    // 我们这边置空就会在析构时跳过，否则同一个指针被释放两次。
    void Release() {
        model = nullptr;
        data = nullptr;
    }
};

// 按 opt 把现场准备好（成功返回 true；失败返回 false，原因已经打到 stderr，调用方直接返回 1）。
// 过程里的那几行 printf 是给"跑一下看看"用的摘要：换模型/换场景时最先要看的几个数都在这里。
inline bool Prepare(const cli::Options &opt, Scene *out) {
    // 默认场景：从可执行文件所在目录**往上找**带 scenes/ 的那一层。比"往上数两层"健壮：
    // <任务目录>/cpp/build/ 与 <任务目录>/cpp/essential/build/ 两种位置都适用。
    const fs::path exe_dir = fs::read_symlink("/proc/self/exe").parent_path();
    fs::path root;
    for (fs::path p = exe_dir; p != p.parent_path(); p = p.parent_path()) {
        if (fs::is_directory(p / "scenes")) {
            root = p;
            break;
        }
    }
    if (opt.scene.empty() && root.empty()) {
        std::fprintf(stderr, "从可执行文件所在目录往上找不到带 scenes/ 的任务目录：%s\n",
                     exe_dir.c_str());
        std::fprintf(stderr, "请用第一个参数指定场景，或按 README 的构建命令重新构建。\n");
        return false;
    }
    const fs::path scene = opt.scene.empty() ? root / "scenes/flat_scene.xml" : opt.scene;
    out->scene_path = scene; // 官方界面的 Load() 要一个名字（也写进日志，便于对照）

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

    // 脚（4 个足底碰撞球）+ 站姿文件
    out->feet = stance::FindFeet(m, &out->foot_radius);
    const std::vector<int> &feet = out->feet;
    std::printf("脚：%zu 个足底碰撞球（半径 %.3f m）\n", feet.size(), out->foot_radius);
    if (feet.size() != 4) {
        std::fprintf(stderr, "没找到 4 个足底球，模型不对？\n");
        return false;
    }
    // 站姿：不搜索，从文件加载（见文件头第三条）——文件是完整版用 stance::Search 搜出来写的
    const fs::path stance_path =
        opt.stance_file.empty() ? root / "models/stance.txt" : opt.stance_file;
    std::string stance_err;
    if (!stance::LoadFromFile(stance_path, m, feet, out->foot_radius, &out->target, &stance_err)) {
        std::fprintf(stderr, "站姿文件加载失败：%s\n  原因：%s\n", stance_path.c_str(),
                     stance_err.c_str());
        std::fprintf(stderr,
                     "  重新生成（用完整版搜一次并写下来）：\n"
                     "    pixi run @20260927_motor/cpp/build/motor_sim --dump-stance %s\n",
                     stance_path.c_str());
        return false;
    }
    const stance::Target &target = out->target;
    std::printf("站姿（从 %s 加载）：基座 z=%.4f m\n", stance_path.c_str(), target.z);

    if (!start::Pose(m, d, opt.start, target))
        return false;
    out->ref[0] = d->qpos[0]; // 漂移参考点 = 起点基座位置
    out->ref[1] = d->qpos[1];
    out->ref[2] = d->qpos[2];
    return true;
}

} // namespace setup
