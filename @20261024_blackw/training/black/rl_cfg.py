"""RL configuration for Black velocity tasks.

`black_ppo_runner_cfg` 与 `him_rl_cfg.black_him_runner_cfg` 共用同一份
`BLACK_CONFIG` 数值来源；这里提供两个共享 helper，供 PPO / HIMPPO 两条路径复用，
避免 HIM 复制一套 PPO 超参数。
"""

import os
from dataclasses import dataclass
from typing import Literal

from mjlab.rl import (
    RslRlModelCfg,
    RslRlOnPolicyRunnerCfg,
    RslRlPpoAlgorithmCfg,
)

from .black_config import BLACK_CONFIG


def black_ppo_algorithm_kwargs() -> dict:
    """PPO 算法超参数映射（普通 PPO 与 HIMPPO 唯一来源：BLACK_CONFIG.algorithm）。"""
    algorithm = BLACK_CONFIG.algorithm
    return {
        "value_loss_coef": algorithm.value_loss_coef,
        "use_clipped_value_loss": algorithm.use_clipped_value_loss,
        "clip_param": algorithm.clip_param,
        "entropy_coef": algorithm.entropy_coef,
        "num_learning_epochs": algorithm.num_learning_epochs,
        "num_mini_batches": algorithm.num_mini_batches,
        "learning_rate": algorithm.learning_rate,
        "schedule": algorithm.schedule,
        "gamma": algorithm.gamma,
        "lam": algorithm.lam,
        "desired_kl": algorithm.desired_kl,
        "max_grad_norm": algorithm.max_grad_norm,
        "normalize_advantage_per_mini_batch": (
            algorithm.normalize_advantage_per_mini_batch),
        # Guarded fine-tuning registers a PPO subclass (weight-space trust region).
        "class_name": os.environ.get("BLACKW_ALGORITHM", "PPO"),
    }


def black_critic_model_cfg() -> RslRlModelCfg:
    """critic model cfg（普通 PPO 与 HIMPPO 共用）。"""
    policy = BLACK_CONFIG.policy
    return RslRlModelCfg(
        hidden_dims=policy.critic_hidden_dims,
        activation=policy.activation,
        obs_normalization=policy.critic_obs_normalization,
    )


def black_actor_distribution_cfg() -> dict:
    """actor Gaussian distribution cfg（普通 PPO 与 HIMPPO 共用）。"""
    policy = BLACK_CONFIG.policy
    return {
        "class_name": "GaussianDistribution",
        "init_std": policy.initial_std,
        "std_type": policy.std_type,
        "learn_std": policy.learn_std,
    }


@dataclass
class BlackRslRlOnPolicyRunnerCfg(RslRlOnPolicyRunnerCfg):
    """Black PPO runner cfg：新增 command curriculum checkpoint 恢复模式。

    ``command_curriculum_restore``（见 curriculum_checkpoint.resolve_restore_mode）：

    ```text
    auto  （默认）：同 stage resume -> full；跨 stage resume -> range；
                  旧 checkpoint（无 curriculum state） -> none + warning
    full  ：逐值恢复 range / EMA / streak / buffer（同 stage 精确续训）
    range ：只恢复 vx range，统计 fresh（跨 stage / 跨训练条件 continuation）
    none  ：不恢复，保持 config 初始范围
    ```
    """

    command_curriculum_restore: str = "auto"


def black_ppo_runner_cfg(
    stage: Literal["flat", "rough", "gravel_flat", "gravel_free", "depth"],
) -> BlackRslRlOnPolicyRunnerCfg:
    policy = BLACK_CONFIG.policy
    runner = BLACK_CONFIG.runner
    if stage not in ("flat", "rough", "gravel_flat", "gravel_free", "depth"):
        raise ValueError(f"unknown Black training stage: {stage}")
    stage_runner = getattr(runner, stage)
    return BlackRslRlOnPolicyRunnerCfg(
        command_curriculum_restore=runner.command_curriculum_restore,
        actor=RslRlModelCfg(
            hidden_dims=policy.actor_hidden_dims,
            activation=policy.activation,
            # Black policy 直接使用已固定 scale 的 45 维 observation，
            # 不做 running normalization（critic 保持 True）。
            obs_normalization=policy.actor_obs_normalization,
            distribution_cfg=black_actor_distribution_cfg(),
        ),
        critic=black_critic_model_cfg(),
        algorithm=RslRlPpoAlgorithmCfg(**black_ppo_algorithm_kwargs()),
        seed=runner.seed,
        experiment_name=runner.experiment_name,
        run_name=stage_runner.run_name,
        load_run=stage_runner.load_run,
        save_interval=runner.save_interval,
        num_steps_per_env=runner.num_steps_per_env,
        max_iterations=runner.max_iterations,
        # 与部署一致的动作截断（rl_sar clip_actions=±100）；也防 NaN/怪动作外溢。
        clip_actions=BLACK_CONFIG.control.action_clip,
    )


# Depth CNN encoder: 64x48 -> 32x24 -> 16x12 -> 8x6, then global average pool
# -> 64-D latent.  Input resolution is read from the env observation shape, so a
# `BLACK_DEPTH_WIDTH/HEIGHT` cost A/B needs no change here.
DEPTH_CNN_CFG = {
    "output_channels": (16, 32, 64),
    "kernel_size": (5, 3, 3),
    "stride": (2, 2, 2),
    "padding": "zeros",
    "global_pool": "avg",
    "flatten": True,
}


def black_depth_ppo_runner_cfg() -> BlackRslRlOnPolicyRunnerCfg:
    """PPO runner cfg for the camera task: blind PPO + depth CNN in the actor.

    Everything (rewards, algorithm, critic layout, command curriculum) is the
    validated blind P1 setup; only the actor becomes ``CNNModel`` and the obs
    group mapping adds the 2-D ``camera`` group.  The blind task stays
    checkpoint-compatible, so the depth task can later warm start from it.
    """
    from dataclasses import replace

    from alldog_mjlab.tasks.velocity.black.camera_depth import CAMERA_OBS_GROUP

    cfg = black_ppo_runner_cfg("depth")
    cfg.actor = replace(cfg.actor, class_name="CNNModel", cnn_cfg=DEPTH_CNN_CFG)
    cfg.obs_groups = {
        "actor": ("actor", CAMERA_OBS_GROUP),
        "critic": ("critic",),
    }
    return cfg
