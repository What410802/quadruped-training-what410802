// 快照握手探针：量 mj_step / mj_copyData / mjv_copyData 的单次耗时，并核对
// "拷贝出来的快照"与物理本体在可视化关心的量上是否逐位一致。
//
// 用途：`docs/learn/runtime-timing.md` §13（把单线程窗口循环拆成物理线程 + 渲染线程）
// 里的数字与结论。构建/运行（仓库根；场景用 @20261005_ros2/scenes/flat_scene.xml）：
//
//     pixi run bash -lc 'g++ -O2 -std=c++17 <本文件> -I"$CONDA_PREFIX/include" -L"$CONDA_PREFIX/lib" -lmujoco -o /tmp/snapshot_copy_bench'
//     pixi run /tmp/snapshot_copy_bench @20261005_ros2/scenes/flat_scene.xml
//
// 输出示例（本机 i5-1035G1、flat_scene、MuJoCo 3.12；三次运行的波动范围）：
//     nq=19 nv=18 ngeom=50 ncon=6
//     mj_step      :  38–44 us
//     mj_copyData  :  71–86 us
//     mjv_copyData :  70–92 us
//     快照 vs 本体：max|dqpos|=0  max|dxpos|=0  max|dgeom_xpos|=0  ncon=8
//     快照独立：20 步后 time 7.002000 -> 7.002000（应不变）
// 说明：Python 绑定只暴露 mj_copyData（没有 mjv_copyData），所以这条要用 C++ 量。

#include <mujoco/mujoco.h>

#include <algorithm>
#include <chrono>
#include <cstdio>

namespace
{
mjModel *model = nullptr;
mjData *live = nullptr;
mjData *snap = nullptr;

double Bench(void (*fn)(), int iterations)
{
    fn(); // 预热
    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < iterations; ++i)
    {
        fn();
    }
    const auto t1 = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::micro>(t1 - t0).count() / iterations;
}

void Step() { mj_step(model, live); }
void CopyFull() { mj_copyData(snap, model, live); }
void CopyForVis() { mjv_copyData(snap, model, live); }

double MaxAbsDiff(const double *a, const double *b, int count)
{
    double worst = 0.0;
    for (int i = 0; i < count; ++i)
    {
        worst = std::max(worst, std::abs(a[i] - b[i]));
    }
    return worst;
}
} // namespace

int main(int argc, char **argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "用法：%s <scene.xml> [iterations]\n", argv[0]);
        return 2;
    }
    const int iterations = argc > 2 ? std::atoi(argv[2]) : 5000;

    char error[1024] = {0};
    model = mj_loadXML(argv[1], nullptr, error, sizeof(error));
    if (model == nullptr)
    {
        std::fprintf(stderr, "加载失败：%s\n", error);
        return 1;
    }
    live = mj_makeData(model);
    snap = mj_makeData(model);
    for (int i = 0; i < 500; ++i) // 到稳态再量（接触已经建立）
    {
        mj_step(model, live);
    }

    std::printf("nq=%ld nv=%ld ngeom=%ld ncon=%ld\n", static_cast<long>(model->nq),
                static_cast<long>(model->nv), static_cast<long>(model->ngeom),
                static_cast<long>(live->ncon));
    std::printf("mj_step      : %7.1f us\n", Bench(Step, iterations));
    std::printf("mj_copyData  : %7.1f us\n", Bench(CopyFull, iterations));
    std::printf("mjv_copyData : %7.1f us\n", Bench(CopyForVis, iterations));

    mj_forward(model, live);
    mjv_copyData(snap, model, live);
    std::printf("快照 vs 本体：max|dqpos|=%.3g  max|dxpos|=%.3g  max|dgeom_xpos|=%.3g  ncon=%ld\n",
                MaxAbsDiff(snap->qpos, live->qpos, model->nq),
                MaxAbsDiff(snap->xpos, live->xpos, 3 * model->nbody),
                MaxAbsDiff(snap->geom_xpos, live->geom_xpos, 3 * model->ngeom),
                static_cast<long>(snap->ncon));

    // 快照是独立副本：之后继续步进物理，快照不该被改动
    const double time_before = snap->time;
    for (int i = 0; i < 20; ++i)
    {
        mj_step(model, live);
    }
    std::printf("快照独立：20 步后 time %.6f -> %.6f（应不变）\n", time_before, snap->time);

    mj_deleteData(live);
    mj_deleteData(snap);
    mj_deleteModel(model);
    return 0;
}
