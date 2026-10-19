// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include <cmath>
#include <chrono>
#include <algorithm>
#include <limits>
#include <vector>
#include <utility>
#include "safety_motion.hpp"
#include "nav2_core/controller.hpp"
#include "nav2_costmap_2d/footprint_collision_checker.hpp"
#include "nav2_core/controller_exceptions.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"
#include "tf2/utils.hpp"

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
    costmap_ = costmap;
    auto node = parent.lock();
    logger_ = node->get_logger();
    clock_ = node->get_clock();
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
    auto parameter = [&](const std::string & key, double value) {
        if (!node->has_parameter(name + "." + key)) {
          node->declare_parameter(name + "." + key, value);
        }
        return node->get_parameter(name + "." + key).as_double();
      };
    safety_.reaction = parameter("safety_reaction_time", .25);
    safety_.linear_decel = parameter("safety_linear_decel", .5);
    safety_.angular_decel = parameter("safety_angular_decel", 2.);
    safety_.horizon = parameter("safety_lookahead", 1.);
    slow_distance_ = parameter("safety_slow_distance", .4);
    slow_speed_ = parameter("safety_slow_linear_speed", .32);
    auto within = [](double v, double low, double high) {
        return std::isfinite(v) && v >= low && v <= high;
      };
    if (!within(safety_.reaction, .05, 1.) ||
      !within(safety_.linear_decel, .1, 3.) ||
      !within(safety_.angular_decel, .2, 10.) ||
      !within(safety_.horizon, .5, 3.) || safety_.horizon < safety_.reaction ||
      !within(slow_distance_, .05, .8) || !within(slow_speed_, .1, .4))
    {
      throw std::runtime_error("Invalid safety buffer / stopping model parameters");
    }
    loader_ = std::make_unique<pluginlib::ClassLoader<nav2_core::Controller>>(
      "nav2_core", "nav2_core::Controller");
    mppi_ = loader_->createSharedInstance("nav2_rotation_shim_controller::RotationShimController");
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
        return Validate(
          pose, rpp_->computeVelocityCommands(pose, velocity, checker), velocity);
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
    return Validate(
      pose, mppi_->computeVelocityCommands(pose, velocity, checker), velocity);
  }

private:
  geometry_msgs::msg::TwistStamped Validate(
    const geometry_msgs::msg::PoseStamped & pose,
    const geometry_msgs::msg::TwistStamped & command,
    const geometry_msgs::msg::Twist & actual_velocity)
  {
    auto local_pose = pose;
    if (pose.header.frame_id != costmap_->getGlobalFrameID()) {
      try {
        local_pose = tf_->transform(pose, costmap_->getGlobalFrameID(), tf2::durationFromSec(.1));
      } catch (const tf2::TransformException & e) {
        throw nav2_core::ControllerTFError(e.what());
      }
    }
    auto * grid = costmap_->getCostmap();
    std::unique_lock<nav2_costmap_2d::Costmap2D::mutex_t> lock(*grid->getMutex());
    nav2_costmap_2d::FootprintCollisionChecker<nav2_costmap_2d::Costmap2D *> collision(grid);
    const auto footprint = costmap_->getRobotFootprint();
    const safety::Pose start{local_pose.pose.position.x, local_pose.pose.position.y,
      tf2::getYaw(local_pose.pose.orientation)};
    const safety::Velocity actual{actual_velocity.linear.x, actual_velocity.linear.y,
      actual_velocity.angular.z};
    auto output = command;
    if (footprint.size() < 3 || !safety::finite(actual) ||
      !safety::finite({output.twist.linear.x, output.twist.linear.y, output.twist.angular.z}) ||
      !std::isfinite(start.x) || !std::isfinite(start.y) || !std::isfinite(start.yaw))
    {
      throw nav2_core::NoValidControl("Invalid footprint, measured velocity or controller output");
    }
    auto inside = [&](double x, double y) {
        bool result = false;
        for (size_t i = 0, j = footprint.size() - 1; i < footprint.size(); j = i++) {
          const auto & a = footprint[i]; const auto & b = footprint[j];
          if (((a.y > y) != (b.y > y)) &&
            x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x)
          {result = !result;}
        }
        return result;
      };
    auto point_distance = [&](double x, double y) {
        if (inside(x, y)) {return 0.0;}
        double best = std::numeric_limits<double>::infinity();
        for (size_t i = 0, j = footprint.size() - 1; i < footprint.size(); j = i++) {
          const auto & a = footprint[i]; const auto & b = footprint[j];
          const double dx = b.x - a.x, dy = b.y - a.y;
          const double length = dx * dx + dy * dy;
          const double t = length > 1e-12 ?
            std::clamp(((x - a.x) * dx + (y - a.y) * dy) / length, 0., 1.) : 0.;
          best = std::min(best, std::hypot(x - a.x - t * dx, y - a.y - t * dy));
        }
        return best;
      };
    double radius = 0.;
    for (const auto & point : footprint) {radius = std::max(radius, std::hypot(point.x, point.y));}
    const double cell_radius = std::sqrt(2.) * grid->getResolution() / 2.;
    // Collect nearby lethal/unknown cell centres once, not for every rollout pose.
    std::vector<std::pair<double, double>> occupied;
    for (unsigned int my = 0; my < grid->getSizeInCellsY(); ++my) {
      for (unsigned int mx = 0; mx < grid->getSizeInCellsX(); ++mx) {
        if (grid->getCost(mx, my) < nav2_costmap_2d::LETHAL_OBSTACLE) {continue;}
        double x, y; grid->mapToWorld(mx, my, x, y);
        occupied.emplace_back(x, y);
      }
    }
    const auto safe = [&](const safety::Pose & p) {
        unsigned int mx, my;
        if (!grid->worldToMap(p.x, p.y, mx, my) ||
          grid->getCost(mx, my) >= nav2_costmap_2d::INSCRIBED_INFLATED_OBSTACLE)
        {return false;}
        const double c = std::cos(p.yaw), sn = std::sin(p.yaw);
        // All corners must remain within the observed local costmap.
        for (const auto & point : footprint) {
          if (!grid->worldToMap(p.x + c * point.x - sn * point.y,
            p.y + sn * point.x + c * point.y, mx, my)) {return false;}
        }
        const auto cost = collision.footprintCostAtPose(p.x, p.y, p.yaw, footprint);
        if (cost < 0. || cost >= nav2_costmap_2d::LETHAL_OBSTACLE) {return false;}
        // Native edge checks alone can miss a small obstacle entirely inside the body.
        for (const auto & point : occupied) {
          const double dx = point.first - p.x, dy = point.second - p.y;
          if (dx * dx + dy * dy > (radius + cell_radius) * (radius + cell_radius)) {continue;}
          if (inside(c * dx + sn * dy, -sn * dx + c * dy)) {return false;}
        }
        return true;
      };
    if (!safety::stoppingClear(start, actual, safety_, safe)) {
      throw nav2_core::NoValidControl("Measured stopping envelope blocked; pause/replan required");
    }
    double clearance = std::numeric_limits<double>::infinity();
    const double c = std::cos(start.yaw), sn = std::sin(start.yaw);
    for (const auto & point : occupied) {
      const double dx = point.first - start.x, dy = point.second - start.y;
      if (dx * dx + dy * dy >
        (radius + slow_distance_ + cell_radius) * (radius + slow_distance_ + cell_radius)) {continue;}
      clearance = std::min(clearance,
        std::max(0., point_distance(c * dx + sn * dy, -sn * dx + c * dy) - cell_radius));
    }
    const double speed = std::hypot(output.twist.linear.x, output.twist.linear.y);
    if (clearance < slow_distance_ && speed > slow_speed_) {
      const double ratio = slow_speed_ / speed;
      output.twist.linear.x *= ratio;
      output.twist.linear.y *= ratio;
      RCLCPP_INFO_THROTTLE(logger_, *clock_, 3000,
        "Safety buffer: clearance %.3fm, requested %.3fm/s capped at %.3fm/s",
        clearance, speed, slow_speed_);
    }
    const safety::Velocity desired{output.twist.linear.x, output.twist.linear.y,
      output.twist.angular.z};
    if (!safety::commandClear(start, actual, desired, safety_, safe)) {
      throw nav2_core::NoValidControl("Command / measured transition envelope blocked");
    }
    // Revalidate after limiting; never increase a small controller command.
    return output;
  }

  safety::Settings safety_;
  double slow_distance_{.4}, slow_speed_{.32};
  rclcpp::Clock::SharedPtr clock_;
  std::shared_ptr<nav2_costmap_2d::Costmap2DROS> costmap_;
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
