// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include "nav2_mppi_controller/critic_function.hpp"
#include "pluginlib/class_list_macros.hpp"

namespace mppi::critics
{
// A soft trajectory preference, never a post-processing velocity multiplier.
// Collision critics still score the original trajectories and can reject them.
class Lite3ResponseCritic : public CriticFunction
{
public:
  void initialize() override
  {
    auto get = parameters_handler_->getParamGetter(name_);
    get(weight_, "cost_weight", 10.0f);
    get(linear_, "linear_reference", 0.28f);
    get(angular_, "angular_reference", 0.45f);
    get(near_goal_, "disable_near_goal", 0.8f);
    get(horizon_, "evaluation_horizon", 0.6f);
    if (!(weight_ >= 0 && linear_ > 0 && angular_ > 0 && near_goal_ > 0 && horizon_ > 0)) {
      throw std::runtime_error("Invalid Lite3ResponseCritic parameters");
    }
  }

  void score(CriticData & data) override
  {
    if (!enabled_ || std::hypot(data.goal.position.x - data.state.pose.pose.position.x,
      data.goal.position.y - data.state.pose.pose.position.y) <= near_goal_)
    {
      return;  // Final RPP/MPPI approach must be allowed to slow down and stop.
    }
    const auto steps = std::min(data.state.cvx.shape()[1],
      static_cast<size_t>(std::max(1.0f, horizon_ / data.model_dt)));
    for (size_t row = 0; row < data.costs.size(); ++row) {
      float sum = 0;
      for (size_t col = 0; col < steps; ++col) {
        const float translation = std::hypot(data.state.cvx(row, col),
          data.state.cvy(row, col)) / linear_;
        const float rotation = std::abs(data.state.cwz(row, col)) / angular_;
        const float ratio = std::min(1.0f, std::max(translation, rotation));
        // Zero remains a valid wait; useful translations/rotations cost zero.
        // Small nonzero commands that produce almost no gait cost more.
        sum += 4.0f * ratio * (1.0f - ratio);
      }
      if (steps) {data.costs(row) += weight_ * sum / steps;}
    }
  }

private:
  float weight_, linear_, angular_, near_goal_, horizon_;
};
}  // namespace mppi::critics

PLUGINLIB_EXPORT_CLASS(mppi::critics::Lite3ResponseCritic, mppi::critics::CriticFunction)
