#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "lite3_interfaces/action/navigate_task.hpp"
#include "nav2_msgs/action/compute_path_to_pose.hpp"
#include "nav2_msgs/action/follow_path.hpp"
#include "std_srvs/srv/set_bool.hpp"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_listener.h"

using namespace std::chrono_literals;
using Navigate = lite3_interfaces::action::NavigateTask;
using ComputePath = nav2_msgs::action::ComputePathToPose;
using FollowPath = nav2_msgs::action::FollowPath;
using MissionHandle = rclcpp_action::ServerGoalHandle<Navigate>;
using PlanHandle = rclcpp_action::ClientGoalHandle<ComputePath>;
using FollowHandle = rclcpp_action::ClientGoalHandle<FollowPath>;
using SetBool = std_srvs::srv::SetBool;
using Clock = std::chrono::steady_clock;

// 一个执行器串行处理状态和回调；等待外部响应时不阻塞执行器。
class MissionManager : public rclcpp::Node
{
public:
  MissionManager() : Node("mission_manager")
  {
    const auto & overrides = get_node_parameters_interface()->get_parameter_overrides();
    if (overrides.count("goal_x") || overrides.count("goal_y") || overrides.count("goal_yaw")) {
      throw std::invalid_argument(
              "mission_manager现在等待Action任务；旧启动参数方式请运行mission_manager_once");
    }
    task_timeout_ = PositiveParameter("task_timeout", 120.0);
    server_timeout_ = PositiveParameter("server_timeout", 5.0);
    cleanup_timeout_ = PositiveParameter("cleanup_timeout", 5.0);
    pose_max_age_ = PositiveParameter("pose_max_age", 1.0);
    start_xy_tolerance_ = PositiveParameter("start_xy_tolerance", 0.5);
    start_yaw_tolerance_ = PositiveParameter("start_yaw_tolerance", 0.5);
    goal_xy_tolerance_ = PositiveParameter("goal_xy_tolerance", 0.25);
    goal_yaw_tolerance_ = PositiveParameter("goal_yaw_tolerance", 0.25);
    buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    listener_ = std::make_unique<tf2_ros::TransformListener>(*buffer_, this, false);
    planner_ = rclcpp_action::create_client<ComputePath>(this, "/compute_path_to_pose");
    controller_ = rclcpp_action::create_client<FollowPath>(this, "/follow_path");
    mode_ = create_client<SetBool>("/lite3/set_navigation_mode");
    stop_ = create_client<SetBool>("/lite3/set_stop");
    server_ = rclcpp_action::create_server<Navigate>(
      this, "/navigate_task",
      [this](const rclcpp_action::GoalUUID &, std::shared_ptr<const Navigate::Goal>) {
        if (busy_ || fault_latched_) {
          RCLCPP_WARN(get_logger(), "拒绝新任务：已有任务，或上次清理尚未确认");
          return rclcpp_action::GoalResponse::REJECT;
        }
        busy_ = true;  // 在 accepted 回调之前预留位置，防止同时接受两个目标。
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      },
      [](std::shared_ptr<MissionHandle>) {
        return rclcpp_action::CancelResponse::ACCEPT;
      },
      [this](std::shared_ptr<MissionHandle> handle) {
        task_ = std::make_shared<Task>();
        task_->handle = handle;
        task_->started = task_->phase_started = task_->last_feedback = Clock::now();
        RCLCPP_INFO(get_logger(), "接收导航任务：目标 (%.2f, %.2f)，朝向 %.2f rad",
          handle->get_goal()->goal_x, handle->get_goal()->goal_y,
          handle->get_goal()->goal_yaw);
      });
    timer_ = create_wall_timer(50ms, [this]() {Tick();});
    RCLCPP_INFO(get_logger(), "任务节点已启动，等待 /navigate_task；一次只接受一个任务");
  }

private:
  struct Task
  {
    std::shared_ptr<MissionHandle> handle;
    std::string phase = "WAITING_SYSTEM";
    Clock::time_point started, phase_started, last_feedback;
    geometry_msgs::msg::PoseStamped pose;
    bool pose_valid = false;
    double remaining = std::numeric_limits<double>::quiet_NaN();
    bool plan_pending = false, follow_pending = false;
    PlanHandle::SharedPtr plan_handle;
    FollowHandle::SharedPtr follow_handle;
    bool plan_cancel_sent = false, follow_cancel_sent = false;
    bool stopping = false, stop_sent = false, stop_confirmed = false, ended = false;
    int64_t stop_request_id = 0;
    uint16_t result_code = Navigate::Result::SYSTEM_ERROR;
    std::string message;
  };

  double PositiveParameter(const std::string & name, double value)
  {
    const auto result = declare_parameter<double>(name, value);
    if (!std::isfinite(result) || result <= 0.0) {
      throw std::invalid_argument(name + " 必须是正的有限数");
    }
    return result;
  }

  static double Seconds(Clock::time_point start)
  {
    return std::chrono::duration<double>(Clock::now() - start).count();
  }

  static double Yaw(const geometry_msgs::msg::Quaternion & q)
  {
    return std::atan2(2.0 * (q.w * q.z + q.x * q.y),
      1.0 - 2.0 * (q.y * q.y + q.z * q.z));
  }

  static double AngleError(double a, double b)
  {
    return std::abs(std::atan2(std::sin(a - b), std::cos(a - b)));
  }

  bool ReadPose(geometry_msgs::msg::PoseStamped & pose)
  {
    try {
      const auto tf = buffer_->lookupTransform("map", "base_footprint", tf2::TimePointZero);
      const double age = (now() - rclcpp::Time(tf.header.stamp, get_clock()->get_clock_type())).seconds();
      if (age > pose_max_age_ || age < -0.1) {return false;}
      const auto & p = tf.transform.translation;
      const auto & q = tf.transform.rotation;
      const double norm = q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w;
      if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z) ||
        !std::isfinite(norm) || std::abs(norm - 1.0) > 0.01)
      {return false;}
      pose.header = tf.header;
      pose.pose.position.x = p.x;
      pose.pose.position.y = p.y;
      pose.pose.position.z = p.z;
      pose.pose.orientation = q;
      return true;
    } catch (const tf2::TransformException &) {
      return false;
    }
  }

  void Phase(const std::shared_ptr<Task> & t, const std::string & phase)
  {
    t->phase = phase;
    t->phase_started = Clock::now();
    RCLCPP_INFO(get_logger(), "任务阶段：%s", phase.c_str());
  }

  void Tick()
  {
    auto t = task_;
    if (!t) {return;}
    if (t->ended) {CancelChildren(t); return;}
    t->pose_valid = ReadPose(t->pose);
    if (t->handle->is_canceling() && !t->stopping) {
      StopTask(t, Navigate::Result::CANCELED, "用户取消导航任务");
    }
    if (!t->stopping && Seconds(t->started) >= task_timeout_) {
      StopTask(t, Navigate::Result::TIMEOUT, "任务超过总时间预算");
    }
    if (t->stopping) {
      Cleanup(t);
    } else if (t->phase == "WAITING_SYSTEM") {
      const auto g = t->handle->get_goal();
      if (!std::isfinite(g->goal_x) || !std::isfinite(g->goal_y) ||
        !std::isfinite(g->goal_yaw) || (g->check_start &&
        (!std::isfinite(g->start_x) || !std::isfinite(g->start_y) || !std::isfinite(g->start_yaw))))
      {
        StopTask(t, Navigate::Result::INVALID_GOAL, "目标或检查起点不是有效数字");
      } else if (t->pose_valid && planner_->action_server_is_ready() &&
        controller_->action_server_is_ready() && mode_->service_is_ready() && stop_->service_is_ready())
      {
        if (g->check_start &&
          (std::hypot(t->pose.pose.position.x - g->start_x, t->pose.pose.position.y - g->start_y) > start_xy_tolerance_ ||
          AngleError(Yaw(t->pose.pose.orientation), g->start_yaw) > start_yaw_tolerance_))
        {
          StopTask(t, Navigate::Result::START_MISMATCH, "填写的起点与实际 map 位姿不一致");
        } else {
          SelectNavigation(t);
        }
      } else if (Seconds(t->phase_started) >= server_timeout_) {
        StopTask(t, Navigate::Result::SYSTEM_ERROR, "等待地图TF、Nav2或运动服务超时");
      }
    } else if (t->phase == "SELECTING_NAVIGATION" && Seconds(t->phase_started) >= server_timeout_) {
      StopTask(t, Navigate::Result::SYSTEM_ERROR, "切换导航模式响应超时");
    } else if ((t->phase == "PLANNING" || t->phase == "FOLLOWING") && !t->pose_valid) {
      StopTask(t, Navigate::Result::SYSTEM_ERROR, "map 到 base_footprint 的位姿失效或过期");
    }
    if (!t->ended && Seconds(t->last_feedback) >= 1.0) {
      auto feedback = std::make_shared<Navigate::Feedback>();
      feedback->phase = t->phase;
      if (t->pose_valid) {feedback->current_pose = t->pose;}
      feedback->remaining_distance = t->remaining;
      feedback->replan_count = 0;
      t->handle->publish_feedback(feedback);
      t->last_feedback = Clock::now();
    }
  }

  void SelectNavigation(const std::shared_ptr<Task> & t)
  {
    Phase(t, "SELECTING_NAVIGATION");
    auto request = std::make_shared<SetBool::Request>();
    request->data = true;  // 选择导航来源，但不解除停止锁定。
    mode_->async_send_request(request, [this, t](rclcpp::Client<SetBool>::SharedFuture future) {
      if (t != task_ || t->stopping || t->ended) {return;}
      if (!future.get()->success) {
        StopTask(t, Navigate::Result::SYSTEM_ERROR, "运动节点拒绝导航模式：" + future.get()->message);
        return;
      }
      RCLCPP_INFO(get_logger(), "%s；已有停止锁定必须由用户显式解除", future.get()->message.c_str());
      BeginPlanning(t);
    });
  }

  void BeginPlanning(const std::shared_ptr<Task> & t)
  {
    Phase(t, "PLANNING");
    const auto g = t->handle->get_goal();
    ComputePath::Goal request;
    request.goal.header.frame_id = "map";
    request.goal.pose.position.x = g->goal_x;
    request.goal.pose.position.y = g->goal_y;
    request.goal.pose.orientation.z = std::sin(g->goal_yaw / 2.0);
    request.goal.pose.orientation.w = std::cos(g->goal_yaw / 2.0);
    request.planner_id = "GridBased";
    request.use_start = false;  // 规划器始终从实际当前位置开始。
    t->plan_pending = true;
    rclcpp_action::Client<ComputePath>::SendGoalOptions options;
    options.goal_response_callback = [this, t](PlanHandle::SharedPtr handle) {
      t->plan_pending = false;
      t->plan_handle = handle;
      if (t->stopping || t->ended) {CancelChildren(t); return;}
      if (!handle) {StopTask(t, Navigate::Result::SYSTEM_ERROR, "规划器拒绝请求");}
    };
    options.result_callback = [this, t](const PlanHandle::WrappedResult & result) {
      t->plan_handle.reset();
      if (t != task_ || t->stopping || t->ended) {return;}
      if (!result.result) {StopTask(t, Navigate::Result::SYSTEM_ERROR, "规划器没有有效结果"); return;}
      if (result.code != rclcpp_action::ResultCode::SUCCEEDED || result.result->error_code != 0) {
        const auto code = result.result->error_code;
        uint16_t mapped = Navigate::Result::SYSTEM_ERROR;
        if (code == ComputePath::Result::GOAL_OUTSIDE_MAP || code == ComputePath::Result::GOAL_OCCUPIED) {
          mapped = Navigate::Result::INVALID_GOAL;
        } else if (code == ComputePath::Result::NO_VALID_PATH) {
          mapped = Navigate::Result::NO_PATH;
        }
        StopTask(t, mapped, "规划失败，Nav2码 " + std::to_string(code) + "：" + result.result->error_msg);
        return;
      }
      const auto & path = result.result->path;
      if (path.poses.empty() || path.header.frame_id != "map") {
        StopTask(t, Navigate::Result::SYSTEM_ERROR, "规划路线为空或坐标系不是 map"); return;
      }
      for (const auto & p : path.poses) {
        if ((!p.header.frame_id.empty() && p.header.frame_id != "map") ||
          !std::isfinite(p.pose.position.x) || !std::isfinite(p.pose.position.y))
        {StopTask(t, Navigate::Result::SYSTEM_ERROR, "规划路线有无效点"); return;}
      }
      RCLCPP_INFO(get_logger(), "获得完整路线：%zu个点", path.poses.size());
      BeginFollowing(t, path);
    };
    planner_->async_send_goal(request, options);
  }

  void BeginFollowing(const std::shared_ptr<Task> & t, const nav_msgs::msg::Path & path)
  {
    Phase(t, "FOLLOWING");
    FollowPath::Goal request;
    request.path = path;  // 直接使用规划器结果，不转发 /plan 话题。
    request.controller_id = "FollowPath";
    request.goal_checker_id = "goal_checker";
    request.progress_checker_id = "progress_checker";
    t->follow_pending = true;
    rclcpp_action::Client<FollowPath>::SendGoalOptions options;
    options.goal_response_callback = [this, t](FollowHandle::SharedPtr handle) {
      t->follow_pending = false;
      t->follow_handle = handle;
      if (t->stopping || t->ended) {CancelChildren(t); return;}
      if (!handle) {StopTask(t, Navigate::Result::SYSTEM_ERROR, "控制器拒绝路线");}
    };
    options.feedback_callback = [t](FollowHandle::SharedPtr, std::shared_ptr<const FollowPath::Feedback> feedback) {
      if (!t->stopping && !t->ended && std::isfinite(feedback->distance_to_goal)) {
        t->remaining = feedback->distance_to_goal;
      }
    };
    options.result_callback = [this, t](const FollowHandle::WrappedResult & result) {
      t->follow_handle.reset();
      if (t != task_ || t->stopping || t->ended) {return;}
      if (!result.result || result.code != rclcpp_action::ResultCode::SUCCEEDED || result.result->error_code != 0) {
        const std::string detail = result.result ?
          "Nav2码 " + std::to_string(result.result->error_code) + "：" + result.result->error_msg : "无有效结果";
        // 没有阻挡重试/跌倒检测时，不把控制器失败误称为 BLOCKED/MOTION_FAILED。
        StopTask(t, Navigate::Result::SYSTEM_ERROR, "路线跟随失败：" + detail); return;
      }
      if (t->handle->is_canceling()) {StopTask(t, Navigate::Result::CANCELED, "用户取消任务"); return;}
      const auto g = t->handle->get_goal();
      t->pose_valid = ReadPose(t->pose);
      if (!t->pose_valid ||
        std::hypot(t->pose.pose.position.x - g->goal_x, t->pose.pose.position.y - g->goal_y) > goal_xy_tolerance_ ||
        AngleError(Yaw(t->pose.pose.orientation), g->goal_yaw) > goal_yaw_tolerance_)
      {
        StopTask(t, Navigate::Result::SYSTEM_ERROR, "控制器报告成功，但最终 map 位姿未通过目标容差检查"); return;
      }
      t->remaining = 0.0;
      Finish(t, Navigate::Result::SUCCESS, "已到达目标；等待下一次任务", false);
    };
    controller_->async_send_goal(request, options);
  }

  void StopTask(const std::shared_ptr<Task> & t, uint16_t code, const std::string & message)
  {
    if (t->stopping || t->ended) {return;}
    t->stopping = true;
    t->result_code = code;
    t->message = message;
    Phase(t, "STOPPING");
    Cleanup(t);
  }

  void CancelChildren(const std::shared_ptr<Task> & t)
  {
    if (t->plan_handle && !t->plan_cancel_sent) {
      t->plan_cancel_sent = true;
      planner_->async_cancel_goal(t->plan_handle);
    }
    if (t->follow_handle && !t->follow_cancel_sent) {
      t->follow_cancel_sent = true;
      controller_->async_cancel_goal(t->follow_handle);
    }
  }

  void Cleanup(const std::shared_ptr<Task> & t)
  {
    // 先锁定速度；结果回调确认 Nav2 任务结束后才释放忙碌状态。
    if (!t->stop_sent && stop_->service_is_ready()) {
      t->stop_sent = true;
      auto request = std::make_shared<SetBool::Request>();
      request->data = true;
      auto future = stop_->async_send_request(request,
        [t](rclcpp::Client<SetBool>::SharedFuture response) {
          t->stop_confirmed = response.get()->success;
        });
      t->stop_request_id = future.request_id;
    }
    CancelChildren(t);
    const bool children_done = !t->plan_pending && !t->follow_pending &&
      !t->plan_handle && !t->follow_handle;
    if (children_done && t->stop_confirmed) {
      Finish(t, t->result_code, t->message + "；导航任务已结束，运动停止锁定保持开启", false);
    } else if (Seconds(t->phase_started) >= cleanup_timeout_) {
      if (t->stop_sent) {stop_->remove_pending_request(t->stop_request_id);}
      Finish(t, Navigate::Result::SYSTEM_ERROR,
        t->message + "；未能确认停止锁定或下游任务结束，拒绝后续任务。请检查旧任务后重启任务节点", true);
    }
  }

  void Finish(const std::shared_ptr<Task> & t, uint16_t code, const std::string & message, bool fault)
  {
    auto result = std::make_shared<Navigate::Result>();
    result->result_code = code;
    result->message = message;
    if (t->pose_valid) {result->final_pose = t->pose;}
    else {result->message += "；最终位姿不可用（final_pose.frame_id为空）";}
    result->retry_count = 0;
    t->ended = true;
    fault_latched_ = fault;
    RCLCPP_INFO(get_logger(), "任务结束：编号 %u，%s", static_cast<unsigned>(code), result->message.c_str());
    if (t->handle->is_canceling()) {t->handle->canceled(result);}
    else if (code == Navigate::Result::SUCCESS) {t->handle->succeed(result);}
    else {t->handle->abort(result);}
    if (!fault) {task_.reset(); busy_ = false;}
    // 故障时保留 Task，晚到的 Nav2 接受响应仍会触发取消；绝不覆盖旧任务。
  }

  bool busy_ = false, fault_latched_ = false;
  double task_timeout_, server_timeout_, cleanup_timeout_, pose_max_age_;
  double start_xy_tolerance_, start_yaw_tolerance_, goal_xy_tolerance_, goal_yaw_tolerance_;
  std::shared_ptr<Task> task_;
  std::unique_ptr<tf2_ros::Buffer> buffer_;
  std::unique_ptr<tf2_ros::TransformListener> listener_;
  rclcpp_action::Server<Navigate>::SharedPtr server_;
  rclcpp_action::Client<ComputePath>::SharedPtr planner_;
  rclcpp_action::Client<FollowPath>::SharedPtr controller_;
  rclcpp::Client<SetBool>::SharedPtr mode_, stop_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  try {
    rclcpp::spin(std::make_shared<MissionManager>());
  } catch (const std::exception & error) {
    RCLCPP_ERROR(rclcpp::get_logger("mission_manager"), "%s", error.what());
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
