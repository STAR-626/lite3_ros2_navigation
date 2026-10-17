// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include <cmath>
#include <chrono>
#include "nav2_core/controller.hpp"
#include "nav2_core/controller_exceptions.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"

namespace lite3_navigation
{
// Reuse native collision-aware controllers. MPPI handles local detours; RPP
// handles the final short approach and explicit in-place goal rotation, which
// has already been validated with this RL policy. No extra ROS node or output
// publisher, and no unvalidated hand-written bypass of collision checking.
class AvoidanceController : public nav2_core::Controller
{
public:
  void configure(const rclcpp_lifecycle::LifecycleNode::WeakPtr & parent,
    std::string name, std::shared_ptr<tf2_ros::Buffer> tf,
    std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap) override
  {
    tf_ = tf;
    auto node = parent.lock();
    logger_ = node->get_logger();
    if (!node->has_parameter(name + ".goal_approach_distance")) {
      node->declare_parameter(name + ".goal_approach_distance", 0.65);
    }
    node->get_parameter(name + ".goal_approach_distance", approach_distance_);
    if (!std::isfinite(approach_distance_) || approach_distance_ <= .25) {
      throw std::runtime_error("goal_approach_distance must exceed goal tolerance");
    }
    if (!node->has_parameter(name + ".goal_approach_retry")) {
      node->declare_parameter(name + ".goal_approach_retry", 2.0);
    }
    node->get_parameter(name + ".goal_approach_retry", approach_retry_);
    if (!std::isfinite(approach_retry_) || approach_retry_ <= 0.) {
      throw std::runtime_error("goal_approach_retry must be positive");
    }
    loader_ = std::make_unique<pluginlib::ClassLoader<nav2_core::Controller>>(
      "nav2_core", "nav2_core::Controller");
    mppi_ = loader_->createSharedInstance("nav2_mppi_controller::MPPIController");
    rpp_ = loader_->createSharedInstance(
      "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController");
    mppi_->configure(parent, name, tf, costmap);
    rpp_->configure(parent, name + ".GoalApproach", tf, costmap);
  }
  void activate() override {mppi_->activate(); rpp_->activate();}
  void deactivate() override {mppi_->deactivate(); rpp_->deactivate();}
  void cleanup() override {mppi_->cleanup(); rpp_->cleanup();}
  void reset() override {mppi_->reset(); rpp_->reset(); approach_ = false; retry_after_ = Steady::now();}
  bool cancel() override {return approach_ ? rpp_->cancel() : mppi_->cancel();}
  void setSpeedLimit(const double & speed, const bool & percentage) override
  {mppi_->setSpeedLimit(speed, percentage); rpp_->setSpeedLimit(speed, percentage);}

  void setPlan(const nav_msgs::msg::Path & path) override
  {
    if (path.poses.empty()) {throw nav2_core::InvalidPath("Empty path");}
    goal_ = path.poses.back();
    goal_.header.frame_id = path.header.frame_id;
    goal_.header.stamp = builtin_interfaces::msg::Time();
    approach_ = false;
    retry_after_ = Steady::now();
    mppi_->setPlan(path);
    rpp_->setPlan(path);
  }

  geometry_msgs::msg::TwistStamped computeVelocityCommands(
    const geometry_msgs::msg::PoseStamped & pose,
    const geometry_msgs::msg::Twist & velocity, nav2_core::GoalChecker * checker) override
  {
    geometry_msgs::msg::PoseStamped goal;
    try {
      goal = goal_.header.frame_id == pose.header.frame_id ? goal_ :
        tf_->transform(goal_, pose.header.frame_id, tf2::durationFromSec(.1));
    } catch (const tf2::TransformException & e) {
      throw nav2_core::ControllerTFError(e.what());
    }
    const double distance = std::hypot(pose.pose.position.x - goal.pose.position.x,
      pose.pose.position.y - goal.pose.position.y);
    const bool approach = distance < approach_distance_ + (approach_ ? .15 : 0.0) &&
      Steady::now() >= retry_after_;
    if (approach != approach_) {
      RCLCPP_INFO(logger_, "%s", approach ?
        "Goal approach: native RPP with in-place rotation and collision checks" :
        "Local avoidance: native MPPI");
      if (!approach) {mppi_->reset();}
      approach_ = approach;
    }
    if (approach_) {
      try {
        return rpp_->computeVelocityCommands(pose, velocity, checker);
      } catch (const nav2_core::NoValidControl & e) {
        // A valid SE2 route may still need a local reverse manoeuvre near the
        // goal. RPP's forward/rotate approach cannot execute it. Return to the
        // collision-aware MPPI rather than repeatedly selecting the same RPP.
        approach_ = false;
        retry_after_ = Steady::now() + std::chrono::duration_cast<Steady::duration>(
          std::chrono::duration<double>(approach_retry_));
        mppi_->reset();
        RCLCPP_WARN(logger_, "Goal approach blocked; native MPPI manoeuvre before retry: %s", e.what());
      }
    }
    return mppi_->computeVelocityCommands(pose, velocity, checker);
  }

private:
  // Instances must be destroyed before their plugin loader.
  std::unique_ptr<pluginlib::ClassLoader<nav2_core::Controller>> loader_;
  nav2_core::Controller::Ptr mppi_, rpp_;
  std::shared_ptr<tf2_ros::Buffer> tf_;
  geometry_msgs::msg::PoseStamped goal_;
  rclcpp::Logger logger_{rclcpp::get_logger("lite3_avoidance")};
  using Steady = std::chrono::steady_clock;
  Steady::time_point retry_after_{Steady::now()};
  double approach_retry_{2.0};
  double approach_distance_{.65};
  bool approach_{false};
};
}  // namespace lite3_navigation
PLUGINLIB_EXPORT_CLASS(lite3_navigation::AvoidanceController, nav2_core::Controller)
