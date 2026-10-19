// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <algorithm>
#include <cmath>

namespace lite3_navigation::safety
{
struct Pose {double x, y, yaw;};
struct Velocity {double x, y, yaw;};
struct Settings
{
  double reaction{0.25};
  double linear_decel{0.5};
  double angular_decel{2.0};
  double horizon{1.0};
};
inline bool finite(const Velocity & v)
{
  return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.yaw);
}
inline Velocity worldVelocity(const Velocity & body, double yaw)
{
  return {body.x * std::cos(yaw) - body.y * std::sin(yaw),
    body.x * std::sin(yaw) + body.y * std::cos(yaw), body.yaw};
}
inline Velocity approach(const Velocity & current, const Velocity & target,
  double linear_delta, double angular_delta)
{
  const double dx = target.x - current.x, dy = target.y - current.y;
  const double distance = std::hypot(dx, dy);
  const double ratio = distance > linear_delta ? linear_delta / distance : 1.0;
  return {current.x + ratio * dx, current.y + ratio * dy,
    current.yaw + std::clamp(target.yaw - current.yaw, -angular_delta, angular_delta)};
}
inline void advance(Pose & p, const Velocity & a, const Velocity & b, double dt)
{
  p.x += .5 * (a.x + b.x) * dt;
  p.y += .5 * (a.y + b.y) * dt;
  p.yaw += .5 * (a.yaw + b.yaw) * dt;
}
// Velocity is integrated in the world frame: a zero new command does not
// erase measured momentum. Settings are hypotheses requiring RL calibration.
template<class Safe>
bool stoppingClear(Pose pose, const Velocity & actual, const Settings & cfg, Safe safe)
{
  if (!finite(actual) || !safe(pose)) {return false;}
  auto current = worldVelocity(actual, pose.yaw);
  double elapsed = 0.0;
  constexpr double step = .025;
  while (elapsed < cfg.reaction - 1e-9) {
    const double dt = std::min(step, cfg.reaction - elapsed);
    advance(pose, current, current, dt);
    elapsed += dt;
    if (!safe(pose)) {return false;}
  }
  const double stop_time = std::max(std::hypot(current.x, current.y) / cfg.linear_decel,
    std::abs(current.yaw) / cfg.angular_decel);
  // Reject physically implausible odometry instead of unbounded simulation.
  if (!std::isfinite(stop_time) || stop_time > 10.0) {return false;}
  elapsed = 0.0;
  while (elapsed < stop_time - 1e-9) {
    const double dt = std::min(step, stop_time - elapsed);
    const auto next = approach(current, {0., 0., 0.}, cfg.linear_decel * dt,
      cfg.angular_decel * dt);
    advance(pose, current, next, dt);
    current = next;
    elapsed += dt;
    if (!safe(pose)) {return false;}
  }
  return true;
}
template<class Safe>
bool commandClear(Pose pose, const Velocity & actual, const Velocity & command,
  const Settings & cfg, Safe safe)
{
  if (!finite(actual) || !finite(command) || !safe(pose)) {return false;}
  const auto initial_pose = pose;
  auto current = worldVelocity(actual, pose.yaw);
  double elapsed = 0.0;
  constexpr double step = .025;
  while (elapsed < cfg.horizon - 1e-9) {
    double dt = std::min(step, cfg.horizon - elapsed);
    Velocity next = current;
    if (elapsed < cfg.reaction - 1e-9) {
      dt = std::min(dt, cfg.reaction - elapsed);
    } else {
      const auto target = worldVelocity(command, pose.yaw + .5 * current.yaw * dt);
      next = approach(current, target, cfg.linear_decel * dt, cfg.angular_decel * dt);
    }
    advance(pose, current, next, dt);
    current = next;
    elapsed += dt;
    if (!safe(pose)) {return false;}
  }
  // Also check the original instantaneous-command prediction. It guards
  // against an RL response faster than our assumed transition model.
  pose = initial_pose;
  elapsed = 0.0;
  while (elapsed < cfg.horizon - 1e-9) {
    const double dt = std::min(step, cfg.horizon - elapsed);
    const auto v = worldVelocity(command, pose.yaw + .5 * command.yaw * dt);
    advance(pose, v, v, dt);
    elapsed += dt;
    if (!safe(pose)) {return false;}
  }
  return true;
}
}  // namespace lite3_navigation::safety
