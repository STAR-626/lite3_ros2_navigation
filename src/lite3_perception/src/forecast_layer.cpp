// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include <chrono>
#include <cmath>
#include <mutex>
#include <vector>
#include "nav2_costmap_2d/layer.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "sensor_msgs/point_cloud2_iterator.hpp"
#include "tf2/LinearMath/Quaternion.hpp"
#include "tf2/LinearMath/Transform.hpp"

namespace lite3_perception
{
// Forecast is a separate, expiring overlay. It never edits measured clouds or
// ray-clearing buffers. Old bounds are always included so the layered master
// resets them and rebuilds static/voxel costs before this layer marks new cells.
class ForecastLayer : public nav2_costmap_2d::Layer
{
public:
  void onInitialize() override
  {
    declareParameter("enabled", rclcpp::ParameterValue(true));
    declareParameter("timeout", rclcpp::ParameterValue(0.5));
    auto node = node_.lock();
    node->get_parameter(name_ + ".enabled", enabled_);
    node->get_parameter(name_ + ".timeout", timeout_);
    if (!std::isfinite(timeout_) || timeout_ <= 0.0) {
      throw std::runtime_error("Invalid forecast timeout");
    }
    current_ = true;  // Actual sensor freshness is enforced by the voxel layer.
    rclcpp::SubscriptionOptions options;
    options.callback_group = callback_group_;
    subscription_ = node->create_subscription<sensor_msgs::msg::PointCloud2>(
      "/lite3/perception/forecast", rclcpp::SensorDataQoS().keep_last(1),
      [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr message) {
        std::lock_guard<std::mutex> lock(mutex_);
        latest_ = message;
        received_ = std::chrono::steady_clock::now();
      }, options);
  }

  void reset() override
  {
    std::lock_guard<std::mutex> lock(mutex_);
    latest_.reset();  // Keep old active bounds until the next master rebuild.
  }
  bool isClearable() override {return true;}

  void updateBounds(double, double, double, double * min_x, double * min_y,
    double * max_x, double * max_y) override
  {
    auto include = [&](const tf2::Vector3 & p) {
      const double margin = layered_costmap_->getCostmap()->getResolution();
      *min_x = std::min(*min_x, p.x() - margin);
      *min_y = std::min(*min_y, p.y() - margin);
      *max_x = std::max(*max_x, p.x() + margin);
      *max_y = std::max(*max_y, p.y() + margin);
    };
    for (const auto & p : active_) {include(p);}
    active_.clear();
    std::lock_guard<std::mutex> lock(mutex_);
    if (!enabled_ || !latest_) {return;}
    const double wall_age = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - received_).count();
    const double age = (clock_->now() - rclcpp::Time(latest_->header.stamp)).seconds();
    if (age < -0.05 || age > timeout_ || wall_age > 1.0) {return;}
    try {
      tf2::Transform transform;
      transform.setIdentity();
      if (latest_->header.frame_id != layered_costmap_->getGlobalFrameID()) {
        const auto t = tf_->lookupTransform(layered_costmap_->getGlobalFrameID(),
          latest_->header.frame_id, rclcpp::Time(latest_->header.stamp)).transform;
        transform = tf2::Transform(tf2::Quaternion(t.rotation.x, t.rotation.y,
          t.rotation.z, t.rotation.w), tf2::Vector3(t.translation.x, t.translation.y, t.translation.z));
      }
      sensor_msgs::PointCloud2ConstIterator<float> x(*latest_, "x"), y(*latest_, "y"), z(*latest_, "z");
      for (; x != x.end(); ++x, ++y, ++z) {
        if (!std::isfinite(*x) || !std::isfinite(*y) || !std::isfinite(*z)) {continue;}
        const auto p = transform * tf2::Vector3(*x, *y, *z);
        active_.push_back(p);
        include(p);
      }
    } catch (const std::exception & e) {
      active_.clear();
      RCLCPP_WARN_THROTTLE(logger_, *clock_, 2000, "Forecast discarded: %s", e.what());
    }
  }

  void updateCosts(nav2_costmap_2d::Costmap2D & grid,
    int min_i, int min_j, int max_i, int max_j) override
  {
    for (const auto & p : active_) {
      unsigned int x, y;
      if (grid.worldToMap(p.x(), p.y(), x, y) &&
        static_cast<int>(x) >= min_i && static_cast<int>(x) < max_i &&
        static_cast<int>(y) >= min_j && static_cast<int>(y) < max_j)
      {
        grid.setCost(x, y, nav2_costmap_2d::LETHAL_OBSTACLE);
      }
    }
  }

private:
  double timeout_{0.5};
  std::mutex mutex_;
  sensor_msgs::msg::PointCloud2::ConstSharedPtr latest_;
  std::chrono::steady_clock::time_point received_;
  std::vector<tf2::Vector3> active_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
};
}  // namespace lite3_perception
PLUGINLIB_EXPORT_CLASS(lite3_perception::ForecastLayer, nav2_costmap_2d::Layer)
