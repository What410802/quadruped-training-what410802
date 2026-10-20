// Scene viewer for this task: load one MJCF, step the physics, render with the
// self-written GLFW window (viewer.h reused from @20260927_motor). Policy
// inference is intentionally not wired in yet; see cpp/README.md.

#include <mujoco/mujoco.h>

#include <cstdio>
#include <cstring>
#include <memory>

#include "viewer.h"

namespace {

struct ModelDeleter
{
    void operator()(mjModel* m) const
    {
        if (m != nullptr)
        {
            mj_deleteModel(m);
        }
    }
};

struct DataDeleter
{
    void operator()(mjData* d) const
    {
        if (d != nullptr)
        {
            mj_deleteData(d);
        }
    }
};

void PrintUsage(const char* argv0)
{
    std::printf("Usage: %s --scene <path-to-mjcf> [--width N] [--height N] [--paused]\n", argv0);
    std::printf("Keys: Space = pause/resume, R = reset, Esc/Q = quit\n");
}

} // namespace

int main(int argc, char** argv)
{
    const char* scene = nullptr;
    int width = 1280;
    int height = 720;
    bool paused = false;
    for (int i = 1; i < argc; ++i)
    {
        if (std::strcmp(argv[i], "--scene") == 0 && i + 1 < argc)
        {
            scene = argv[++i];
        }
        else if (std::strcmp(argv[i], "--width") == 0 && i + 1 < argc)
        {
            width = std::atoi(argv[++i]);
        }
        else if (std::strcmp(argv[i], "--height") == 0 && i + 1 < argc)
        {
            height = std::atoi(argv[++i]);
        }
        else if (std::strcmp(argv[i], "--paused") == 0)
        {
            paused = true;
        }
        else
        {
            PrintUsage(argv[0]);
            return 1;
        }
    }
    if (scene == nullptr)
    {
        PrintUsage(argv[0]);
        return 1;
    }

    char error[1024] = {};
    std::unique_ptr<mjModel, ModelDeleter> model(mj_loadXML(scene, nullptr, error, sizeof(error)));
    if (model == nullptr)
    {
        std::fprintf(stderr, "Failed to load MJCF: %s\n", error);
        return 1;
    }
    std::unique_ptr<mjData, DataDeleter> data(mj_makeData(model.get()));
    if (data == nullptr)
    {
        std::fprintf(stderr, "Failed to allocate mjData\n");
        return 1;
    }
    mj_forward(model.get(), data.get());

    std::printf("Loaded %s: nq=%ld nv=%ld nu=%ld ngeom=%ld\n", scene,
                static_cast<long>(model->nq), static_cast<long>(model->nv),
                static_cast<long>(model->nu), static_cast<long>(model->ngeom));
    std::fflush(stdout);

    viewer::Window window(model.get(), "locomotion scene viewer", width, height);
    double last_print = -1.0;
    while (window.Poll())
    {
        int key = 0;
        while (window.TakeKey(&key))
        {
            if (key == GLFW_KEY_ESCAPE || key == GLFW_KEY_Q)
            {
                return 0;
            }
            if (key == GLFW_KEY_SPACE)
            {
                paused = !paused;
            }
            if (key == GLFW_KEY_R)
            {
                mj_resetData(model.get(), data.get());
                mj_forward(model.get(), data.get());
            }
        }
        if (!paused)
        {
            mj_step(model.get(), data.get());
        }
        char hud_left[128];
        char hud_right[128];
        std::snprintf(hud_left, sizeof(hud_left), "scene: %s", scene);
        std::snprintf(hud_right, sizeof(hud_right), "%s t=%.2fs", paused ? "PAUSED" : "RUN",
                      data->time);
        window.Draw(model.get(), data.get(), hud_left, hud_right);
        if (data->time - last_print >= 5.0)
        {
            last_print = data->time;
            std::printf("t=%.2f s\n", data->time);
            std::fflush(stdout);
        }
    }
    return 0;
}
