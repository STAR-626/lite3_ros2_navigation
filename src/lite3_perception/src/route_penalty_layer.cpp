// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include <chrono>
#include <cmath>
#include <mutex>
#include <vector>
#include "nav2_costmap_2d/layer.hpp"
#include "nav_msgs/msg/path.hpp"
#include "pluginlib/class_list_macros.hpp"

namespace lite3_perception
{
// A short-lived preference against recently unexecutable path sections.
// Cost stays below collision thresholds. This is NOT a sensor obstacle layer.
class RoutePenaltyLayer : public nav2_costmap_2d::Layer
{
public:
  void onInitialize() override
  {
    declareParameter("timeout", rclcpp::ParameterValue(12.0));
    declareParameter("radius", rclcpp::ParameterValue(0.18));
    declareParameter("cost", rclcpp::ParameterValue(200));
    auto node = node_.lock();
    node->get_parameter(name_ + ".timeout", timeout_);
    node->get_parameter(name_ + ".radius", radius_);
    node->get_parameter(name_ + ".cost", cost_);
    if (!std::isfinite(timeout_) || timeout_ <= 0 || !std::isfinite(radius_) ||
      radius_ <= 0 || cost_ <= 0 || cost_ >= nav2_costmap_2d::INSCRIBED_INFLATED_OBSTACLE)
    {throw std::runtime_error("Invalid route preference parameters");}
    enabled_ = true;
    current_ = true;
    rclcpp::SubscriptionOptions options;
    options.callback_group = callback_group_;
    sub_ = node->create_subscription<nav_msgs::msg::Path>(
      "/lite3/avoidance/failed_route", rclcpp::QoS(1).reliable().transient_local(),
      [this](nav_msgs::msg::Path::ConstSharedPtr path) {
        std::lock_guard<std::mutex> lock(mutex_);
        latest_ = path;
        received_ = std::chrono::steady_clock::now();
      }, options);
  }

  void reset() override
  {
    std::lock_guard<std::mutex> lock(mutex_);
    latest_.reset();
  }
  bool isClearable() override {return true;}

  void updateBounds(double, double, double, double * min_x, double * min_y,
    double * max_x, double * max_y) override
  {
    auto include = [&](const geometry_msgs::msg::Point & p) {
      const double extra = radius_ + layered_costmap_->getCostmap()->getResolution();
      *min_x = std::min(*min_x, p.x-extra); *min_y = std::min(*min_y, p.y-extra);
      *max_x = std::max(*max_x, p.x+extra); *max_y = std::max(*max_y, p.y+extra);
    };
    for (const auto & p : active_) {include(p);}
    active_.clear();
    std::lock_guard<std::mutex> lock(mutex_);
    if (!latest_ || latest_->header.frame_id != layered_costmap_->getGlobalFrameID() ||
      std::chrono::duration<double>(std::chrono::steady_clock::now()-received_).count() > timeout_)
    {return;}
    for (const auto & pose : latest_->poses) {
      const auto & p = pose.pose.position;
      if (!std::isfinite(p.x) || !std::isfinite(p.y)) {continue;}
      active_.push_back(p);
      include(p);
    }
  }

  void updateCosts(nav2_costmap_2d::Costmap2D & grid,
    int min_i, int min_j, int max_i, int max_j) override
  {
    const double resolution = grid.getResolution();
    for (const auto & p : active_) {
      int left, bottom, right, top;
      grid.worldToMapEnforceBounds(p.x-radius_, p.y-radius_, left, bottom);
      grid.worldToMapEnforceBounds(p.x+radius_, p.y+radius_, right, top);
      for (int y = std::max(bottom, min_j); y <= std::min(top, max_j-1); ++y) {
        for (int x = std::max(left, min_i); x <= std::min(right, max_i-1); ++x) {
          double wx, wy;
          grid.mapToWorld(x, y, wx, wy);
          if (std::hypot(wx-p.x, wy-p.y) > radius_ + .5*resolution) {continue;}
          const auto old = grid.getCost(x, y);
          // Preserve real obstacles, existing larger cost and unknown cells.
          if (old != nav2_costmap_2d::NO_INFORMATION && old < cost_) {
            grid.setCost(x, y, static_cast<unsigned char>(cost_));
          }
        }
      }
    }
  }

private:
  double timeout_{12.0}, radius_{.18};
  int cost_{200};
  std::mutex mutex_;
  nav_msgs::msg::Path::ConstSharedPtr latest_;
  std::chrono::steady_clock::time_point received_;
  std::vector<geometry_msgs::msg::Point> active_;
  rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr sub_;
};
}  // namespace lite3_perception
PLUGINLIB_EXPORT_CLASS(lite3_perception::RoutePenaltyLayer, nav2_costmap_2d::Layer)
