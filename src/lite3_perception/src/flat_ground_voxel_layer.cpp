// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause

#include <cmath>
#include <algorithm>
#include <memory>
#include "nav2_costmap_2d/voxel_layer.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "sensor_msgs/point_cloud2_iterator.hpp"

namespace lite3_perception
{
// 复用Nav2三维体素算法，只补偿已知平地回波的两格端点退让。
class FlatGroundVoxelLayer : public nav2_costmap_2d::VoxelLayer
{
public:
  void onInitialize() override
  {
    nav2_costmap_2d::VoxelLayer::onInitialize();
    declareParameter("ground_height", rclcpp::ParameterValue(0.005));
    declareParameter("ground_tolerance", rclcpp::ParameterValue(0.02));
    auto node = node_.lock();
    node->get_parameter(name_ + ".ground_height", ground_height_);
    node->get_parameter(name_ + ".ground_tolerance", ground_tolerance_);
    if (!std::isfinite(ground_height_) || !std::isfinite(ground_tolerance_) ||
      ground_tolerance_ < 0.0)
    {
      throw std::runtime_error("Invalid flat ground parameters");
    }
  }

protected:
  void raytraceFreespace(
    const nav2_costmap_2d::Observation & observation,
    double * min_x, double * min_y, double * max_x, double * max_y) override
  {
    if (observation.cloud_->width == 0 || observation.cloud_->height == 0) {
      return;
    }
    // Observation深拷贝点云；原始ROS消息、标记源和其他插件数据均不更改。
    nav2_costmap_2d::Observation corrected(observation);
    sensor_msgs::PointCloud2Iterator<float> x(*corrected.cloud_, "x");
    sensor_msgs::PointCloud2Iterator<float> y(*corrected.cloud_, "y");
    sensor_msgs::PointCloud2Iterator<float> z(*corrected.cloud_, "z");
    const bool tagged = std::any_of(corrected.cloud_->fields.begin(),
      corrected.cloud_->fields.end(), [](const sensor_msgs::msg::PointField & f) {
        return f.name == "ground" && f.datatype == sensor_msgs::msg::PointField::FLOAT32;
      });
    std::unique_ptr<sensor_msgs::PointCloud2Iterator<float>> ground;
    if (tagged) {ground = std::make_unique<sensor_msgs::PointCloud2Iterator<float>>(
        *corrected.cloud_, "ground");}
    for (; x != x.end(); ++x, ++y, ++z) {
      const bool is_ground = tagged ? **ground > .5f :
        std::abs(*z - ground_height_) <= ground_tolerance_;
      if (tagged) {++(*ground);}
      if (!is_ground) {
        continue;
      }
      const double dx = *x - corrected.origin_.x;
      const double dy = *y - corrected.origin_.y;
      const double dz = *z - corrected.origin_.z;
      const double distance = std::sqrt(dx * dx + dy * dy + dz * dz);
      if (distance < 1e-6 || !std::isfinite(distance)) {
        continue;
      }
      // Nav2基类稍后沿同一射线减去2*resolution_；此补偿使最终端点
      // 回到实测地面，不把地面后方/被遮挡区域标为空闲。
      const double scale = (distance + 2.0 * resolution_) / distance;
      *x = corrected.origin_.x + dx * scale;
      *y = corrected.origin_.y + dy * scale;
      *z = corrected.origin_.z + dz * scale;
    }
    nav2_costmap_2d::VoxelLayer::raytraceFreespace(corrected, min_x, min_y, max_x, max_y);
  }

  double ground_height_{0.005};
  double ground_tolerance_{0.02};
};
}  // namespace lite3_perception

PLUGINLIB_EXPORT_CLASS(lite3_perception::FlatGroundVoxelLayer, nav2_costmap_2d::Layer)
