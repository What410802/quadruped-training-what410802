/*
 * New file for @20261007_assignment - no upstream counterpart (package LICENSE covers it).
 *
 * Self-test for include/input_map.hpp: feeds synthetic frames and asserts the resolved intents.
 * It needs no ROS graph, no sim and no hardware - that is the point of moving the key map into a
 * pure function (status.md S3.5). Run it with:
 *
 *     pixi run ros2 run rl_sar input_map_selftest          # 直接跑（最方便）
 *     pixi run bash -lc 'cd @20261007_assignment/ws && colcon test --packages-select rl_sar'   # 走 CTest
 *
 * Exit code 0 = all cases pass, 1 = at least one failed (printed with the observed intents).
 */

#include "input_map.hpp"

#include <cstdio>
#include <string>
#include <vector>

namespace
{

using input_map::Bit;
using input_map::Intent;
using input_map::PadKey;
using input_map::KbKey;

int g_failures = 0;

std::string Names(input_map::IntentMask mask)
{
    std::string out;
    for (std::size_t i = 0; i < input_map::kIntentCount; ++i)
    {
        if (mask & (1u << i))
        {
            if (!out.empty())
            {
                out += "+";
            }
            out += input_map::Name(static_cast<Intent>(i));
        }
    }
    return out.empty() ? "(none)" : out;
}

/// Feed one cycle and return the intents it produced.
input_map::IntentMask Step(std::uint32_t pad, std::uint32_t kb = 0)
{
    input_map::BeginCycle(pad, kb, {});
    return input_map::Current().intents;
}

void Check(const std::string &what, input_map::IntentMask got, input_map::IntentMask want)
{
    const bool ok = got == want;
    if (!ok)
    {
        ++g_failures;
    }
    std::printf("  [%s] %-52s got %-22s want %s\n", ok ? "PASS" : "FAIL", what.c_str(),
                Names(got).c_str(), Names(want).c_str());
}

void ExpectTrue(const std::string &what, bool ok)
{
    if (!ok)
    {
        ++g_failures;
    }
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what.c_str());
}

constexpr std::uint32_t A = Bit(PadKey::A);
constexpr std::uint32_t B = Bit(PadKey::B);
constexpr std::uint32_t X = Bit(PadKey::X);
constexpr std::uint32_t Y = Bit(PadKey::Y);
constexpr std::uint32_t LB = Bit(PadKey::LB);
constexpr std::uint32_t RB = Bit(PadKey::RB);
constexpr std::uint32_t UP = Bit(PadKey::DPadUp);
constexpr std::uint32_t DOWN = Bit(PadKey::DPadDown);

constexpr input_map::IntentMask I(Intent i) { return input_map::Mask(i); }

} // namespace

int main()
{
    std::printf("input_map self-test\n");

    std::printf("① 上升沿天生一次性\n");
    Check("空闲", Step(0), 0);
    Check("按 A", Step(A), I(Intent::StandUp));
    Check("A 一直按着（不应重复）", Step(A), 0);
    Check("松开 A", Step(0), 0);
    Check("再按 A（应再来一次）", Step(A), I(Intent::StandUp));

    std::printf("② 锁存的十字键不再吞按键（P1-h 的回归用例）\n");
    Check("十字键下一直锁存", Step(DOWN), 0);
    Check("锁存着下 + 按 A", Step(DOWN | A), I(Intent::StandUp));
    Check("A 松开、十字键还锁着", Step(DOWN), 0);
    Check("锁存着下 + 按 B", Step(DOWN | B), I(Intent::LieDown));

    std::printf("③ 组合键（十字键是普通 bit，不是特例）\n");
    Check("先按住 RB", Step(RB), 0);
    Check("再按十字键上 → RB+↑ = 进 RL", Step(RB | UP), I(Intent::EnterRL));
    Check("两者都按住（不应重复）", Step(RB | UP), 0);
    Check("松开十字键", Step(RB), 0);
    Check("再按一次十字键上 → 又一次进 RL", Step(RB | UP), I(Intent::EnterRL));
    Check("只按十字键上（没绑行为）", Step(UP), 0);
    Check("先按 LB 再按 X → 阻尼 + 导航翻转（X 本身有绑定）",
          Step(LB | X), I(Intent::Damp) | I(Intent::ToggleNavigation));

    std::printf("③b 电平查询 Held()：给「提前按住、站完再生效」这种手势用\n");
    Step(RB | UP);
    ExpectTrue("RB+↑ 按住时 Held(EnterRL) 为真", input_map::Held(Intent::EnterRL));
    Step(RB);
    ExpectTrue("松开十字键后 Held(EnterRL) 为假", !input_map::Held(Intent::EnterRL));
    ExpectTrue("Held(StandUp) 此时为假（没有按住 A）", !input_map::Held(Intent::StandUp));

    std::printf("④ 按着 RB 再按 A：A 照样生效（旧模型会变成没人认的 RB_A）\n");
    Check("按住 RB", Step(RB), 0);
    Check("RB 还按着时按 A", Step(RB | A), I(Intent::StandUp));
    Check("松开 A（RB 仍按着）", Step(RB), 0);

    std::printf("⑤ 复位组合 RB+Y 与单键 X\n");
    Check("RB+Y → 复位", Step(RB | Y), I(Intent::ResetSim));
    Check("X → 导航模式", Step(X), I(Intent::ToggleNavigation));

    std::printf("⑥ 键盘源：单值锁存，变化即「按下」（终端不报抬起）\n");
    Check("按 0 → 起身", Step(0, Bit(KbKey::Num0)), I(Intent::StandUp));
    Check("0 一直是最后一个键（不应重复）", Step(0, Bit(KbKey::Num0)), 0);
    Check("按 W → 前进微调", Step(0, Bit(KbKey::W)), I(Intent::JogForward));
    Check("再按 1 → 进 RL", Step(0, Bit(KbKey::Num1)), I(Intent::EnterRL));
    Check("按空格 → 清零", Step(0, Bit(KbKey::Space)), I(Intent::ZeroCommand));

    std::printf("⑦ 手柄与键盘可以同时产生意图\n");
    Check("手柄 A + 键盘 1", Step(A, Bit(KbKey::Num1)), I(Intent::StandUp) | I(Intent::EnterRL));

    std::printf("⑧ 轴的映射：十字键上/右为正，且能当 bit 用\n");
    ExpectTrue("axes[7]=+1 → DPadUp 置位",
               input_map::PadMaskFromJoy({0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}, {0, 0, 0, 0, 0, 0, 0, 1}) == UP);
    ExpectTrue("axes[7]=-1 → DPadDown 置位",
               input_map::PadMaskFromJoy({0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}, {0, 0, 0, 0, 0, 0, 0, -1}) == DOWN);
    ExpectTrue("axes[6]=+1 → DPadRight 置位",
               input_map::PadMaskFromJoy({0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}, {0, 0, 0, 0, 0, 0, 1, 0}) ==
               Bit(PadKey::DPadRight));
    ExpectTrue("buttons[5] → RB",
               input_map::PadMaskFromJoy({0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0}, {}) == RB);
    ExpectTrue("长度不够（旧固件只发 6 个按钮）→ 不当成任何按键",
               input_map::PadMaskFromJoy({1, 0, 0}, {0, 0, 0}) == 0);

    if (g_failures == 0)
    {
        std::printf("结论：全部通过 ✓\n");
        return 0;
    }
    std::printf("结论：%d 项未通过 ✗\n", g_failures);
    return 1;
}
