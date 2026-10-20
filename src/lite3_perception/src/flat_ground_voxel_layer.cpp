// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause

#include <cmath>
#include <algorithm>
#include <memory>
#include <cstdint>
#include "occlusion_evidence.hpp"
#include "nav2_costmap_2d/voxel_layer.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "sensor_msgs/point_cloud2_iterator.hpp"

namespace lite3_perception
{
// Native voxel rays plus scan-local occlusion and independent free-space evidence.
class FlatGroundVoxelLayer : public nav2_costmap_2d::VoxelLayer
{
public:
  void onInitialize() override
  {
    nav2_costmap_2d::VoxelLayer::onInitialize();
    declareParameter("ground_height", rclcpp::ParameterValue(0.005));
    declareParameter("ground_tolerance", rclcpp::ParameterValue(0.02));
    declareParameter("clearing_confirmation_frames", rclcpp::ParameterValue(3));
    declareParameter("clearing_occlusion_angle", rclcpp::ParameterValue(0.03));
    auto node = node_.lock();
    node->get_parameter(name_ + ".ground_height", ground_height_);
    node->get_parameter(name_ + ".ground_tolerance", ground_tolerance_);
    node->get_parameter(name_ + ".clearing_confirmation_frames", confirmation_frames_);
    node->get_parameter(name_ + ".clearing_occlusion_angle", occlusion_angle_);
    if (confirmation_frames_ < 1 || confirmation_frames_ > 10 ||
      !std::isfinite(occlusion_angle_) || occlusion_angle_ < 0.0 || occlusion_angle_ > .1)
    {
      throw std::runtime_error("Invalid clearing evidence parameters");
    }
    if (!std::isfinite(ground_height_) || !std::isfinite(ground_tolerance_) ||
      ground_tolerance_ < 0.0)
    {
      throw std::runtime_error("Invalid flat ground parameters");
    }
  }

protected:
  void reset() override
  {
    nav2_costmap_2d::VoxelLayer::reset();
    confirmations_.clear();
    last_stamp_ = -1;
  }

  void raytraceFreespace(
    const nav2_costmap_2d::Observation & observation,
    double * min_x, double * min_y, double * max_x, double * max_y) override
  {
    if (observation.cloud_->width == 0 || observation.cloud_->height == 0) {
      return;
    }
    const auto stamp = rclcpp::Time(observation.cloud_->header.stamp).nanoseconds();
    const std::size_t cells = static_cast<std::size_t>(size_x_) * size_y_;
    // Preserve confirmations for the same world voxels when the rolling local
    // grid shifts; a moving robot must not restart every free-space count.
    if (confirmations_.size() != cells*16 || stamp < last_stamp_ ||
      (last_stamp_ >= 0 && stamp-last_stamp_ > 500000000))
    {
      confirmations_.assign(cells*16, 0);
    } else if (counter_origin_x_ != origin_x_ || counter_origin_y_ != origin_y_) {
      const double shift_x = (origin_x_-counter_origin_x_)/resolution_;
      const double shift_y = (origin_y_-counter_origin_y_)/resolution_;
      const int dx = std::lround(shift_x), dy = std::lround(shift_y);
      std::vector<uint8_t> shifted(cells*16, 0);
      if (std::abs(shift_x-dx) < 1e-5 && std::abs(shift_y-dy) < 1e-5) {
        for (unsigned int y = 0; y < size_y_; ++y) {
          for (unsigned int x = 0; x < size_x_; ++x) {
            const int ox = static_cast<int>(x)+dx, oy = static_cast<int>(y)+dy;
            if (ox >= 0 && oy >= 0 && ox < static_cast<int>(size_x_) &&
              oy < static_cast<int>(size_y_))
            {
              std::copy_n(confirmations_.begin()+(oy*size_x_+ox)*16, 16,
                shifted.begin()+(y*size_x_+x)*16);
            }
          }
        }
      }
      confirmations_.swap(shifted);
    }
    counter_origin_x_ = origin_x_; counter_origin_y_ = origin_y_;
    const bool new_scan = stamp != last_stamp_;
    last_stamp_ = stamp;
    const auto * data = voxel_grid_.getData();
    std::vector<uint32_t> before(data, data+cells);
    OcclusionEvidence visibility(occlusion_angle_);
    const bool has_ground = hasFloatField(*observation.cloud_, "ground");
    const bool has_no_return = hasFloatField(*observation.cloud_, "no_return");
    std::unique_ptr<sensor_msgs::PointCloud2ConstIterator<float>> ground_hit, no_return_hit;
    if (has_ground) {ground_hit = std::make_unique<sensor_msgs::PointCloud2ConstIterator<float>>(
        *observation.cloud_, "ground");}
    if (has_no_return) {no_return_hit = std::make_unique<sensor_msgs::PointCloud2ConstIterator<float>>(
        *observation.cloud_, "no_return");}
    sensor_msgs::PointCloud2ConstIterator<float> hx(*observation.cloud_, "x"),
      hy(*observation.cloud_, "y"), hz(*observation.cloud_, "z");
    for (; hx != hx.end(); ++hx, ++hy, ++hz) {
      const bool floor_hit = has_ground ? **ground_hit > .5f :
        std::abs(*hz-ground_height_) <= ground_tolerance_;
      const bool no_hit = has_no_return && **no_return_hit > .5f;
      if (has_ground) {++(*ground_hit);}
      if (has_no_return) {++(*no_return_hit);}
      const double dx = *hx-observation.origin_.x, dy = *hy-observation.origin_.y,
        dz = *hz-observation.origin_.z;
      const double range = std::sqrt(dx*dx+dy*dy+dz*dz);
      if (!floor_hit && !no_hit && *hz > ground_height_+ground_tolerance_ &&
        range < observation.raytrace_max_range_-.001)
      {
        visibility.add(dx, dy, dz);
      }
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
    auto * after = voxel_grid_.getData();
    const double radius = .5*std::sqrt(2*resolution_*resolution_ + z_resolution_*z_resolution_);
    for (std::size_t i = 0; i < cells; ++i) {
      const auto old_bits = before[i] >> 16;
      if (!old_bits) {continue;}
      const auto removed = old_bits & ~(after[i] >> 16);
      for (int z = 0; z < size_z_; ++z) {
        const uint32_t bit = uint32_t{1} << z;
        auto & count = confirmations_[i*16+z];
        if (!(removed & bit)) {if (new_scan) {count = 0;} continue;}
        double wx, wy, wz;
        mapToWorld3D(i%size_x_, i/size_x_, z, wx, wy, wz);
        const bool hidden = visibility.occluded(wx-observation.origin_.x,
          wy-observation.origin_.y, wz-observation.origin_.z, radius);
        if (hidden) {count = 0;}
        else if (new_scan && count < confirmation_frames_) {++count;}
        if (hidden || count < confirmation_frames_) {
          // Restore this old height bit only, not a whole column or a guessed
          // box. No-return/ground rays still clear visible old occupancy after
          // enough independently stamped scans; hidden records never time out.
          after[i] |= (bit << 16) | bit;
        }
      }
      const auto marked = after[i] >> 16;
      if (!voxel_grid_.bitsBelowThreshold(marked, mark_threshold_)) {
        costmap_[i] = nav2_costmap_2d::LETHAL_OBSTACLE;
        const double wx = origin_x_ + (i%size_x_+.5)*resolution_;
        const double wy = origin_y_ + (i/size_x_+.5)*resolution_;
        touch(wx, wy, min_x, min_y, max_x, max_y);
      }
    }
  }

  static bool hasFloatField(const sensor_msgs::msg::PointCloud2 & cloud, const char * name)
  {
    return std::any_of(cloud.fields.begin(), cloud.fields.end(),
      [name](const auto & f) {return f.name == name &&
        f.datatype == sensor_msgs::msg::PointField::FLOAT32;});
  }
  int confirmation_frames_{3};
  double occlusion_angle_{.03};
  double counter_origin_x_{0.0}, counter_origin_y_{0.0};
  int64_t last_stamp_{-1};
  std::vector<uint8_t> confirmations_;
  double ground_height_{0.005};
  double ground_tolerance_{0.02};
};
}  // namespace lite3_perception

PLUGINLIB_EXPORT_CLASS(lite3_perception::FlatGroundVoxelLayer, nav2_costmap_2d::Layer)
